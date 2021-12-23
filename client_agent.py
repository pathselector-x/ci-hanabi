from sys import argv, stdout
from threading import Thread, Lock, Condition

from numpy.core.numeric import isclose
import GameData
import socket
from constants import *
import numpy as np
from collections import deque
from itertools import product

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
        self.current_hand_knowledge = None #! Holds knowledge about current hand
        self.already_hinted = None #! Holds knowledge about already hinted cards (col, val)

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
                    type(data) is GameData.ServerHintData  or \
                    type(data) is GameData.ServerActionValid or \
                    type(data) is GameData.ServerPlayerMoveOk or \
                    type(data) is GameData.ServerPlayerThunderStrike
                if accepted_types: 
                    self.msg_queue.append(data)
                with self.cv: self.cv.notify_all()

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
                    if type(data) is GameData.ServerActionValid and data.player != self.playerName and data.action == 'discard':
                        done_removing = False
                        for p in self.player_hands:
                            if p.name == data.player:
                                for i, card in enumerate(p.hand):
                                    if card == data.card:
                                        self.already_hinted[p.name].pop(i)
                                        self.already_hinted[p.name].append([False, False])
                                        done_removing = True
                                        break
                                if done_removing: break
                    if (type(data) is GameData.ServerPlayerMoveOk or \
                        type(data) is GameData.ServerPlayerThunderStrike) and data.player != self.playerName:
                        done_removing = False
                        for p in self.player_hands:
                            if p.name == data.player:
                                for i, card in enumerate(p.hand):
                                    if card == data.card:
                                        self.already_hinted[p.name].pop(i)
                                        self.already_hinted[p.name].append([False, False])
                                        done_removing = True
                                        break
                                if done_removing: break
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
                if type(data) is GameData.ServerHintData and data.destination == self.playerName:
                    for i in data.positions: # indices in the current hand
                        self.current_hand_knowledge[i][0 if data.type == 'color' else 1] = data.value
                    read_packets.append(data)
                elif type(data) is GameData.ServerHintData and data.destination != self.playerName:
                    for i in data.positions: # indices in the current hand
                        self.already_hinted[data.destination][i][0 if data.type == 'color' else 1] = True
                    read_packets.append(data) 
            for pkt in read_packets:
                self.msg_queue.remove(pkt)
    
    def calc_deck(self):
        deck = {} #! Holds knowledge about unseen cards
        for col in ['red','yellow','green','blue','white']:
            deck[(col,'1')] = 3
            deck[(col,'2')] = 2
            deck[(col,'3')] = 2
            deck[(col,'4')] = 2
            deck[(col,'5')] = 1

        for player in self.player_hands:
            for card in player.hand:
                deck[(str(card.color), str(card.value))] -= 1

        for col in ['red','yellow','green','blue','white']:
            for card in self.table_cards[col]:
                deck[(str(card.color), str(card.value))] -= 1

        for card in self.discard_pile:
            deck[(str(card.color), str(card.value))] -= 1

        return deck

    def calc_playability(self):
        deck = self.calc_deck()
        piles = {}
        for col in ['red','yellow','green','blue','white']:
            piles[col] = 0
            if len(self.table_cards[col]) > 0:
                piles[col] = int(self.table_cards[col][-1].value)

        playabilities = []
        for card in self.current_hand_knowledge:
            c, v = card
            p = []

            if c != '' and v != '': # I know both col and val
                for col in piles.keys():
                    if c == col and int(v) == piles[col] + 1: p.append(1.0)
                    else: p.append(0.0)

            elif c != '': # I know only the col
                for col in piles.keys():
                    if piles[col] == 5: p.append(0.0)
                    elif c == col: p.append(deck[(c,str(piles[col]+1))] / sum(deck[(c,str(i))] for i in range(1,5+1)))
                    else: p.append(0.0)
            
            elif v != '': # I know only the val
                for col in piles.keys():
                    if piles[col] == 5: p.append(0.0)
                    elif int(v) == piles[col] + 1: p.append(sum(deck[(i,str(v))] for i in ['red','yellow','green','blue','white'] if piles[i] + 1 == int(v)) / sum(deck[(i,str(v))] for i in ['red','yellow','green','blue','white']))
                    else: p.append(0.0)
                
            else: # I don't know anything
                for col in piles.keys():
                    if piles[col] == 5: p.append(0.0)
                    else: p.append(deck[(col,str(piles[col]+1))] / sum(deck[(i,str(j))] for i,j in product(['red','yellow','green','blue','white'], range(1,5+1))))

            playabilities.append(p)

        playabilities = np.asarray(playabilities)
        playabilities = np.max(playabilities, axis=1)
        return playabilities # Each value will be the playability of each single card e.g. [0.06, 0.06, 1.0, 0.06, 0.06]

    def wait_for_turn(self):
        self.query_game_info()
        self.query_game_over()
        #! Check whether it's your turn or the game ended!
        while self.current_player != self.playerName and self.final_score is None:
            with self.cv: self.cv.wait(1.0)
            self.query_game_info()
            self.query_game_over()
        #! Update knowledge
        self.query_game_info()
        self.query_game_over()
        self.query_hints()

    def action_discard(self, num):
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Discard'
        assert self.used_note_tokens > 0, 'Cannot request a Discard when used_note_tokens == 0'
        assert num in range(0, len(self.current_hand_knowledge))
        self.s.send(GameData.ClientPlayerDiscardCardRequest(self.playerName, num).serialize())
        packet_found = False
        while not packet_found:
            with self.lock:
                read_packets = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerActionValid and data.player == self.playerName and data.action == 'discard':
                        packet_found = True
                        read_packets.append(data)
                for pkt in read_packets:
                    self.msg_queue.remove(pkt)
        self.current_hand_knowledge.pop(num)
        self.current_hand_knowledge.append(['', ''])
    
    def action_play(self, num):
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Play'
        assert num in range(0, len(self.current_hand_knowledge))
        self.s.send(GameData.ClientPlayerPlayCardRequest(self.playerName, num).serialize())
        was_a_good_move = False
        packet_found = False
        while not packet_found:
            with self.lock:
                read_packets = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerPlayerThunderStrike:
                        was_a_good_move = False
                        packet_found = True
                        read_packets.append(data)
                    elif type(data) is GameData.ServerPlayerMoveOk:
                        was_a_good_move = True
                        packet_found = True
                        read_packets.append(data)
                for pkt in read_packets:
                    self.msg_queue.remove(pkt)
        self.current_hand_knowledge.pop(num)
        self.current_hand_knowledge.append(['', ''])
        return was_a_good_move

    def action_hint(self, hint_type, dst, value):
        """
        hint_type = 'color' or 'value'
        dst = <player name> : str
        value = if 'color': ['red', 'yellow', 'green', 'blue', 'white'] else [1,2,3,4,5]
        """
        assert self.used_note_tokens < 8, 'Cannot Hint if all note tokens are used'
        assert hint_type in ['color', 'value'], 'hint_type can be "color" or "value"'
        assert dst in [p.name for p in self.player_hands], 'Passed the name of a non-existing player'
        if hint_type == 'color': assert value in ['red','yellow','green','blue','white']
        else: assert value in [1,2,3,4,5]
        self.s.send(GameData.ClientHintData(self.playerName, dst, hint_type, value).serialize())
        packet_found = False
        while not packet_found:
            with self.lock:
                read_packets = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerHintData and data.destination != self.playerName:
                        for i in data.positions: # indices in the current hand
                            self.already_hinted[data.destination][i][0 if data.type == 'color' else 1] = True
                        read_packets.append(data)
                        packet_found = True
                for pkt in read_packets:
                    self.msg_queue.remove(pkt)

    def main_loop(self):
        #! Check how many cards in hand (4 or 5 depending on how many players)
        self.query_game_info()

        self.current_hand_knowledge = [] # Keep track of what you know about your hand
        for _ in range(len(self.player_hands[0].hand)):
            self.current_hand_knowledge.append(['', '']) # color, value
        
        self.already_hinted = {} # Keep track of already hinted cards
        for p in self.player_hands:
            self.already_hinted[p.name] = [[False, False] for _ in range(len(self.player_hands[0].hand))] # color, value

        while True:
            self.wait_for_turn()
            
            #! Check if game ended
            if self.final_score is not None: break

            #TODO: implement logic for auto-play

            playab = self.calc_playability()
            for i in range(len(playab)):
                if playab[i] >= 1.0:
                    self.action_play(i)
                    continue

            self.action_hint('value', self.player_hands[0].name, 1)
            
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

        for p in self.already_hinted.keys():
            print(self.already_hinted[p])


ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
agent = TechnicAngel(ID=ID)

#TODO: Vedere perché si blocca