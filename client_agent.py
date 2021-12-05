from sys import argv, stdout
from threading import Thread, Lock, Condition
import GameData
import socket
from constants import *
from collections import deque

class TechnicAngel:
    def __init__(self, ip=HOST, port=PORT, ID=0):
        self.statuses = ["Lobby", "Game", "GameHint"]
        self.status = self.statuses[0]
        if ID > 0:
            self.playerName = "technic_angel_" + str(ID)
        else:
            self.playerName = "technic_angel"
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        request = GameData.ClientPlayerAddData(self.playerName)
        self.s.connect((ip, port))
        self.s.send(request.serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerConnectionOk:
            print("Connection accepted by the server. Welcome " + self.playerName)
        stdout.flush()

        self.lock = Lock()
        self.cv = Condition()
        self.run = True
        
        # color, value
        self.current_hand_knowledge = None

        self.current_player = None
        self.player_hands = None
        self.table_cards = None
        self.discard_pile = None
        self.used_note_tokens = None
        self.used_storm_tokens = None

        self.final_score = None
        
        #! Ready up your engines...
        self.auto_ready()
        
        self.msg_queue = deque([])
        self.t_listener = Thread(target=self.listener)
        self.t_listener.start()

        self.main_loop()

        with self.lock: 
            self.run = False
            self.s.shutdown(socket.SHUT_RDWR)
        self.t_listener.join()

    def __del__(self):
        self.s.close()

    def listener(self):
        while self.run:
            data = self.s.recv(DATASIZE)
            if not data: continue
            data = GameData.GameData.deserialize(data)
            with self.lock:
                #! Insert in the msg queue just msgs to be processed, ignore the rest
                accepted_types = type(data) is GameData.ServerGameStateData or \
                    type(data) is GameData.ServerGameOver or \
                    (type(data) is GameData.ServerHintData and data.destination == self.playerName) or \
                    type(data) is GameData.ServerActionValid #or \
                    #type(data) is GameData.ServerActionInvalid
                if accepted_types: 
                    self.msg_queue.append(data)
                with self.cv: self.cv.notify_all()

            #if type(data) is GameData.ServerPlayerMoveOk:
            #    print("Nice move!")
            #    print("Current player: " + data.player)
            #if type(data) is GameData.ServerPlayerThunderStrike:
            #    print("OH NO! The Gods are unhappy with you!")

    def auto_ready(self):
        #! Send 'Ready' signal
        self.s.send(GameData.ClientPlayerStartRequest(self.playerName).serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerStartRequestAccepted:
            print("Ready: " + str(data.acceptedStartRequests) + "/"  + str(data.connectedPlayers) + " players")
            data = self.s.recv(DATASIZE)
            data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerStartGameData:
            print("Game start!")
            self.s.send(GameData.ClientPlayerReadyData(self.playerName).serialize())
            self.status = self.statuses[1]

    def query_game_info(self):
        self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
        packet_found = False
        while not packet_found:
            with self.lock:
                read_packets = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerGameStateData:
                        self.current_player = data.currentPlayer
                        self.player_hands = data.players
                        self.table_cards = data.tableCards
                        self.discard_pile = data.discardPile
                        self.used_note_tokens = data.usedNoteTokens
                        self.used_storm_tokens = data.usedStormTokens
                        read_packets.append(data)
                        packet_found = True
                        # Don't break yet. There may be more recent ones to process
                for pkt in read_packets:
                    self.msg_queue.remove(pkt)
                
    def query_game_over(self):
        with self.lock:
            read_packets = []
            for data in self.msg_queue:
                if type(data) is GameData.ServerGameOver:
                    self.final_score = data.score
                    read_packets.append(data)
                    # Don't break yet. There may be more recent ones to process
                    # In this case it's just game over...
            for pkt in read_packets:
                self.msg_queue.remove(pkt)

    def query_hints(self):
        with self.lock:
            read_packets = []
            for data in self.msg_queue:
                if type(data) is GameData.ServerHintData:
                    for i in data.positions: # indices in the current hand
                        self.current_hand_knowledge[i][0 if data.type == 'color' else 1] = data.value
                    read_packets.append(data)
            for pkt in read_packets:
                self.msg_queue.remove(pkt)

    def wait_for_turn(self):
        self.query_game_info()
        self.query_game_over()
        #! Check whether it's your turn or the game ended!
        while self.current_player != self.playerName and self.final_score is None:
            with self.cv: self.cv.wait()
            self.query_game_info()
            self.query_game_over()
        #! Update knowledge
        self.query_game_info()
        self.query_game_over()
        self.query_hints()

    def action_discard(self, num):
        # num = [0, len(hand)-1]: int
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Discard'
        assert self.used_note_tokens > 0, 'Cannot request a Discard when used_note_tokens == 0'
        assert num in range(0, len(self.current_hand_knowledge))
        self.s.send(GameData.ClientPlayerDiscardCardRequest(self.playerName, num).serialize())
        packet_found = False
        while not packet_found:
            with self.lock:
                read_packets = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerActionValid:
                        packet_found = True
                        read_packets.append(data)
                for pkt in read_packets:
                    self.msg_queue.remove(pkt)
        self.current_hand_knowledge.pop(num)
    
    def action_play(self, num, pile_pos): #TODO
        pass 

    def action_hint(self, hint_type, dst, value): #TODO
        pass

    def main_loop(self):
        #! Check how many cards in hand (4 or 5 depending on how many players)
        self.query_game_info()
        self.current_hand_knowledge = []
        for _ in range(len(self.player_hands[0].hand)):
            self.current_hand_knowledge.append(['', '']) # color, value
        
        while True:
            self.wait_for_turn()
            
            #! Check if game ended
            if self.final_score is not None: break

            #TODO: implement logic for auto-play
            
            break
        
        #* This is just for DEBUG
        print(self.current_player)
        for player in self.player_hands:
            print(player.name)
            for card in player.hand:
                print(card.value, card.color)
        print(self.table_cards)

        for card in self.current_hand_knowledge:
            print(card)


ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
agent = TechnicAngel(ID=ID)