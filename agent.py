from sys import argv, stdout
from threading import Thread, Lock, Condition
import time
from numpy.core.numeric import isclose
from numpy.lib.function_base import select
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

        self.lock = Lock()
        self.cv = Condition()
        self.run = True
        
        #! Ready up your engines...
        input('Press enter to start...')
        self.auto_ready()

        self.msg_queue = []
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
            print(type(data))
            with self.lock:
                if type(data) is GameData.ServerInvalidDataReceived:
                    print(data.data)
                    with self.cv: self.cv.notify_all()
                    return

                #! Insert in the msg queue just msgs to be processed, ignore the rest
                accepted_types = type(data) is GameData.ServerGameStateData or \
                    type(data) is GameData.ServerGameOver or \
                    type(data) is GameData.ServerHintData  or \
                    type(data) is GameData.ServerActionValid or \
                    type(data) is GameData.ServerPlayerMoveOk or \
                    type(data) is GameData.ServerPlayerThunderStrike

                if accepted_types: 
                    self.msg_queue.append(data)

                    if type(data) is not GameData.ServerGameStateData:
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

    def calc_deck(self, except_player=None):
        deck = {} #! Holds knowledge about unseen cards
        for col in ['red','yellow','green','blue','white']:
            deck[(col,'1')] = 3
            deck[(col,'2')] = 2
            deck[(col,'3')] = 2
            deck[(col,'4')] = 2
            deck[(col,'5')] = 1

        for player in self.player_hands:
            if except_player is None:
                for card in player.hand:
                    deck[(str(card.color), str(card.value))] -= 1
            elif player.name != except_player:
                for card in player.hand:
                    deck[(str(card.color), str(card.value))] -= 1

        for col in ['red','yellow','green','blue','white']:
            for card in self.table_cards[col]:
                deck[(str(card.color), str(card.value))] -= 1

        for card in self.discard_pile:
            deck[(str(card.color), str(card.value))] -= 1

        return deck

    def calc_playability(self, hand_knowledge, except_player=None):
        deck = self.calc_deck(except_player)
        piles = {}
        for col in ['red','yellow','green','blue','white']:
            piles[col] = 0
            if len(self.table_cards[col]) > 0:
                piles[col] = int(self.table_cards[col][-1].value)

        playabilities = []
        for card in hand_knowledge: #self.current_hand_knowledge: 
            #TODO: if self.current_hand_kn == hand_kn take into account what you know...
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

    def calc_discardability(self):
        deck = self.calc_deck()
        piles = {}
        for col in ['red','yellow','green','blue','white']:
            piles[col] = 0
            if len(self.table_cards[col]) > 0:
                piles[col] = int(self.table_cards[col][-1].value)

        discardabilities = [] 
        for card in self.current_hand_knowledge:
            c, v = card
            p = []

            if c != '' and v != '': # I know both col and val
                for col in piles.keys():
                    if c == col and int(v) <= piles[col]: p.append(1.0)
                    else: p.append(0.0)

            elif c != '': # I know only the col
                for col in piles.keys():
                    if piles[col] == 5: p.append(1.0)
                    elif c == col: p.append(sum(deck[(c,str(i))] for i in range(1,5+1) if i <= piles[col]) / sum(deck[(c,str(i))] for i in range(1,5+1)))
                    else: p.append(1.0)
            
            elif v != '': # I know only the val
                for col in piles.keys():
                    if piles[col] == 5: p.append(1.0)
                    elif int(v) > piles[col]: p.append(sum(deck[(i,str(v))] for i in ['red','yellow','green','blue','white'] if piles[i] >= int(v)) / sum(deck[(i,str(v))] for i in ['red','yellow','green','blue','white']))
                    else: p.append(1.0)
                
            else: # I don't know anything
                for col in piles.keys():
                    if piles[col] == 5: p.append(1.0)
                    else: p.append(sum(deck[(col,str(i))] for i in range(1,5+1) if i <= piles[col]) / sum(deck[(i,str(j))] for i,j in product(['red','yellow','green','blue','white'], range(1,5+1))))

            discardabilities.append(p)

        discardabilities = np.asarray(discardabilities)
        discardabilities = np.min(discardabilities, axis=1)
        return discardabilities # Each value will be the discardability of each single card e.g. [0.06, 0.06, 1.0, 0.06, 0.06]

    def calc_best_hint(self):
        best_so_far = ('value', self.player_hands[0].hand[0].value, self.player_hands[0].name, 0.0) # type, value, dst, playability/utility

        for player in self.player_hands:
            color_hints = ['red','yellow','green','blue','white']
            value_hints = [1,2,3,4,5]
            for card, hint in zip(player.hand, self.already_hinted[player.name]):
                hc, hv = hint
                if hc and card.color in color_hints: color_hints.remove(card.color)
                if hv and card.value in value_hints: value_hints.remove(card.value)
            hc_to_remove = []
            for hc in color_hints:
                if hc not in [card.color for card in player.hand]: hc_to_remove.append(hc)
            hv_to_remove = []
            for hv in value_hints:
                if hv not in [card.value for card in player.hand]: hv_to_remove.append(hv)
            for hc in hc_to_remove: color_hints.remove(hc)
            for hv in hv_to_remove: value_hints.remove(hv)
            
            if len(color_hints) > 0 or len(value_hints) > 0: # at least one useful hint found to deliver
                for vhint in value_hints:
                    simulate_hand = []
                    simulate_hints = []
                    for hint in self.already_hinted[player.name]:
                        simulate_hints.append(hint)
                    for i, card in enumerate(player.hand):
                        if card.value == vhint: simulate_hints[i][1] = True
                    
                    for card, hint in zip(player.hand, simulate_hints):
                        c, v = '', ''
                        hc, hv = hint
                        if hc: c = card.color
                        if hv: v = str(card.value)
                        simulate_hand.append([c,v])
                    
                    utility = np.max(self.calc_playability(simulate_hand, except_player=player.name))
                    if utility > best_so_far[3]:
                        best_so_far = ('value', vhint, player.name, utility)
                
                for chint in color_hints:
                    simulate_hand = []
                    simulate_hints = []
                    for hint in self.already_hinted[player.name]:
                        simulate_hints.append(hint)
                    for i, card in enumerate(player.hand):
                        if card.color == chint: simulate_hints[i][0] = True
                    
                    for card, hint in zip(player.hand, simulate_hints):
                        c, v = '', ''
                        hc, hv = hint
                        if hc: c = card.color
                        if hv: v = str(card.value)
                        simulate_hand.append([c,v])
                    
                    utility = np.max(self.calc_playability(simulate_hand, except_player=player.name))
                    if utility > best_so_far[3]:
                        best_so_far = ('color', chint, player.name, utility)
        print(best_so_far)
        return best_so_far

    def consume_packets(self):
        read_pkts = []
        with self.lock:
            for data in self.msg_queue:

                # Discard data of other players
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
                    read_pkts.append(data)

                # Play data of other players
                elif (type(data) is GameData.ServerPlayerMoveOk or \
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
                    read_pkts.append(data)

                # Hint data: I received a hint
                elif type(data) is GameData.ServerHintData and data.destination == self.playerName:
                    for i in data.positions: # indices in the current hand
                        self.current_hand_knowledge[i][0 if data.type == 'color' else 1] = data.value
                    read_pkts.append(data)

                # Hint data of other players
                elif type(data) is GameData.ServerHintData and data.destination != self.playerName:
                    for i in data.positions: # indices in the current hand
                        self.already_hinted[data.destination][i][0 if data.type == 'color' else 1] = True
                    read_pkts.append(data)
                
                # Game over
                elif type(data) is GameData.ServerGameOver:
                    self.final_score = data.score
                    read_pkts.append(data)
                
                elif type(data) is not GameData.ServerGameStateData:
                    read_pkts.append(data)

            for pkt in read_pkts:
                self.msg_queue.remove(pkt)

    def wait_for_turn(self):
        while self.current_player != self.playerName and self.final_score is None:
            with self.cv: self.cv.wait_for(lambda : False, timeout=1.0)
            self.consume_packets()
            self.action_show()
        self.action_show()
    
    def action_show(self):
        print('Show')
        self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
        found = False
        while not found:
            with self.lock:
                read_pkts = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerGameStateData:
                        self.current_player = data.currentPlayer
                        self.player_hands = data.players
                        self.table_cards = data.tableCards
                        self.discard_pile = data.discardPile
                        self.used_note_tokens = data.usedNoteTokens
                        self.used_storm_tokens = data.usedStormTokens
                        read_pkts.append(data)
                        found = True
                for pkt in read_pkts:
                    self.msg_queue.remove(pkt)
                        
    def action_discard(self, num):
        print('Discard', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Discard'
        assert self.used_note_tokens > 0, 'Cannot request a Discard when used_note_tokens == 0'
        assert num in range(0, len(self.current_hand_knowledge))
        self.s.send(GameData.ClientPlayerDiscardCardRequest(self.playerName, num).serialize())
        self.current_hand_knowledge.pop(num)
        self.current_hand_knowledge.append(['', ''])
        self.current_player = None
        #time.sleep(3.0)
    
    def action_play(self, num):
        print('Play', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Play'
        assert num in range(0, len(self.current_hand_knowledge))
        self.s.send(GameData.ClientPlayerPlayCardRequest(self.playerName, num).serialize())
        self.current_hand_knowledge.pop(num)
        self.current_hand_knowledge.append(['', ''])
        self.current_player = None
        #time.sleep(3.0)
    
    def action_hint(self, hint_type, dst, value):
        print('Hint', hint_type, dst, value)
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
        self.current_player = None
        #time.sleep(3.0)

    def select_action(self, PLAYABILITY_THRESHOLD=1.0):
        playability = self.calc_playability(self.current_hand_knowledge)
        for i in range(len(playability)):
            if playability[i] >= PLAYABILITY_THRESHOLD:
                self.action_play(i)
                return

        if self.used_note_tokens == 8:
            discardability = self.calc_discardability()
            idx_to_discard = np.argmax(discardability)
            self.action_discard(idx_to_discard)
        else:
            best_hint_type, best_hint_val, dst, _ = self.calc_best_hint()
            self.action_hint(best_hint_type, dst, best_hint_val)

    def main_loop(self):
        #! Check how many cards in hand (4 or 5 depending on how many players)
        self.action_show()

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
            self.select_action()
        
        print(f'Final score: {self.final_score}/25')


ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
agent = TechnicAngel(ID=ID)