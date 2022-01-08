from os import read
import os
from sys import argv, stdout
from threading import Thread, Lock, Condition
from itertools import product
import random
from collections import deque
import numpy as np

import GameData
import socket
from constants import *

from game import Card, Game

from hanabi import Hanabi, COLORS
from single_agent_search import SASAgent
import time

class TechnicAngel:
    def __init__(self, ip=HOST, port=PORT, ID=0):
        self.s = None
        self.ID = ID
        if self.ID > 0:
            self.playerName = "technic_angel_" + str(self.ID)
        else:
            self.playerName = "technic_angel"

        self.statuses = ["Lobby", "Game", "GameHint"]
        self.game_ended = False
        self.status = self.statuses[0]
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
        self.play_order = [self.playerName] # relative play order starting from me

        self.current_player = None
        self.player_hands = None
        self.hands_knowledge = None
        self.table_cards = None
        self.discard_pile = None
        self.used_note_tokens = None
        self.used_storm_tokens = None
        self.played_last_turn = None
        self.deck_has_cards = True

        self.final_score = None

        self.lock = Lock()
        self.cv = Condition()
        self.run = True

        self.action_performed = False
        self.satify_show = False
        
        #! Ready up your engines...
        input('Press [ENTER] to start...')
        #time.sleep(3)
        self.auto_ready()

        self.msg_queue = []
        self.t_listener = Thread(target=self.listener)
        self.t_listener.start()

        self.main_loop()
        
    def __del__(self):
        if self.s is not None:
            self.s.close()

    def listener(self):
        try:
            while self.run:
                data = self.s.recv(DATASIZE)
                if not data: continue
                data = GameData.GameData.deserialize(data)
                #print(type(data))
                with self.cv:
                    
                    ## Satisfy check_current_player() request
                    #if type(data) is GameData.ServerGameStateData and self.need_just_cp:
                    #    self.current_player = str(data.currentPlayer)
                    #    self.need_just_cp = False
                    #    self.satify_show = True
                    #    self.cv.notify_all()

                    # Satisfy action_show() request
                    if type(data) is GameData.ServerGameStateData:
                        self.current_player = str(data.currentPlayer)
                        self.player_hands = {self.playerName: []}
                        ##for player in data.players:
                        ##    self.player_hands[player.name] = [Card(card.id, card.value, card.color) for card in player.hand]
                        ##    if self.hands_knowledge is not None:
                        ##        while len(self.player_hands[player.name]) < len(self.hands_knowledge[player.name]):
                        ##            self.deck_has_cards = False
                        ##            self.hands_knowledge[player.name].pop()
                        ##    else:
                        ##        self.play_order.append(player.name) #TODO: refactor this
                        #! === With data.players mod ===
                        play_order = []
                        for player in data.players:
                            if player.name == self.playerName:
                                self.player_hands[player.name] = []
                            else:
                                self.player_hands[player.name] = [Card(card.id, card.value, card.color) for card in player.hand]
                                if self.hands_knowledge is not None:
                                    while len(self.player_hands[player.name]) < len(self.hands_knowledge[player.name]):
                                        self.deck_has_cards = False
                                        self.hands_knowledge[player.name].pop()
                            play_order.append(player.name)
                        play_order = play_order[play_order.index(self.playerName):] + play_order[:play_order.index(self.playerName)]
                        self.play_order = play_order
                        #! === ===
                        self.table_cards = { "red": [], "yellow": [], "green": [], "blue": [], "white": [] }
                        for k in data.tableCards.keys():
                            for card in data.tableCards[k]:
                                self.table_cards[k].append(Card(card.id, card.value, card.color))
                        self.discard_pile = []
                        for card in data.discardPile:
                            self.discard_pile.append(Card(card.id, card.value, card.color))
                        self.used_note_tokens = data.usedNoteTokens
                        self.used_storm_tokens = data.usedStormTokens
                        self.satify_show = True
                        self.cv.notify_all()

                    # Someone other than me played something
                    elif (type(data) is GameData.ServerPlayerMoveOk or \
                        type(data) is GameData.ServerPlayerThunderStrike): #and data.lastPlayer != self.playerName:
                        idx = data.cardHandIndex
                        self.hands_knowledge[data.lastPlayer].pop(idx)
                        self.hands_knowledge[data.lastPlayer].append(['',0])
                        self.current_player = data.player
                        #print('other player PLAY')
                        if data.lastPlayer == self.playerName: self.action_performed = True
                        self.cv.notify_all()

                    # Someone other than me discarded something
                    elif type(data) is GameData.ServerActionValid and data.action == 'discard': #and data.lastPlayer != self.playerName
                        idx = data.cardHandIndex
                        self.hands_knowledge[data.lastPlayer].pop(idx)
                        self.hands_knowledge[data.lastPlayer].append(['',0])
                        self.current_player = data.player
                        if data.lastPlayer == self.playerName: self.action_performed = True
                        self.cv.notify_all()
                    
                    # Someone (including me) hinted another player (I could be the destination too if I didn't hint)
                    elif type(data) is GameData.ServerHintData:
                        for i in data.positions: # indices in the current hand
                            self.hands_knowledge[data.destination][i][0 if data.type == 'color' else 1] = data.value   
                        #print('other player HINT')
                        self.current_player = data.player
                        if data.source == self.playerName: self.action_performed = True
                        self.cv.notify_all()

                    # I played a card
                    #elif (type(data) is GameData.ServerPlayerMoveOk or \
                    #    type(data) is GameData.ServerPlayerThunderStrike) and data.lastPlayer == self.playerName:
                    #    self.action_performed = True
                    #    self.current_player = data.player
                    #    self.cv.notify_all()

                    # I discarded a card
                    #elif type(data) is GameData.ServerActionValid and data.lastPlayer == self.playerName and data.action == 'discard':
                    #    self.action_performed = True
                    #    self.current_player = data.player
                    #    self.cv.notify_all()

                    # Game ended
                    elif type(data) is GameData.ServerGameOver:
                        self.game_ended = True
                        self.final_score = data.score
                        self.cv.notify_all()

        except ConnectionResetError: 
            #with self.cv: 
            self.game_ended = True
            os._exit(0)
                
    def auto_ready(self):
        #! Send 'Ready' signal
        self.s.send(GameData.ClientPlayerStartRequest(self.playerName).serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerStartRequestAccepted:
            print("Ready: " + str(data.acceptedStartRequests) + "/"  + str(data.connectedPlayers) + " players")
            self.position = data.acceptedStartRequests - 1
            data = self.s.recv(DATASIZE)
            data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerStartGameData:
            print("Game start!")
            self.s.send(GameData.ClientPlayerReadyData(self.playerName).serialize())
            self.status = self.statuses[1]

    #def check_current_player(self):
    #    self.need_just_cp = True
    #    self.satify_show = False
    #    self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
    #    while not self.satify_show:
    #        self.cv.wait()

    def action_show(self):
        #self.need_just_cp = False
        self.satify_show = False
        self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
        while not self.satify_show:
            self.cv.wait()

    def action_play(self, num):
        print('Play', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Play'
        assert num in range(len(self.hands_knowledge[self.playerName]))
        self.action_performed = False
        self.s.send(GameData.ClientPlayerPlayCardRequest(self.playerName, num).serialize())
        #self.hands_knowledge[self.playerName].pop(num)
        #if not self.deck_has_cards: 
        #    self.played_last_turn[self.playerName] = True
        #else:
        #    if self.__calc_real_deck_len() - 1 > 0:
        #        self.hands_knowledge[self.playerName].append(['',0])
        #    else:
        #        self.deck_has_cards = False
        while not self.action_performed:
            self.cv.wait()
    
    def action_discard(self, num):
        print('Discard', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Discard'
        assert self.used_note_tokens > 0, 'Cannot request a Discard when used_note_tokens == 0'
        assert num in range(len(self.hands_knowledge[self.playerName]))
        self.action_performed = False
        self.s.send(GameData.ClientPlayerDiscardCardRequest(self.playerName, num).serialize())
        #self.hands_knowledge[self.playerName].pop(num)
        #if not self.deck_has_cards: 
        #    self.played_last_turn[self.playerName] = True
        #else:
        #    if self.__calc_real_deck_len() - 1 > 0:
        #        self.hands_knowledge[self.playerName].append(['',0])
        #    else:
        #        self.deck_has_cards = False
        while not self.action_performed:
            self.cv.wait()
    
    def action_hint(self, hint_type, dst, value):
        print('Hint', hint_type, dst, value)
        """
        hint_type = 'color' or 'value'
        dst = <player name> : str
        value = if 'color': ['red', 'yellow', 'green', 'blue', 'white'] else [1,2,3,4,5]
        """
        assert self.used_note_tokens < 8, 'Cannot Hint if all note tokens are used'
        assert hint_type in ['color', 'value'], 'hint_type can be "color" or "value"'
        assert dst in self.player_hands.keys() and dst != self.playerName, 'Passed the name of a non-existing player'
        if hint_type == 'color': assert value in ['red','yellow','green','blue','white']
        else: assert value in [1,2,3,4,5]
        self.action_performed = False
        self.s.send(GameData.ClientHintData(self.playerName, dst, hint_type, value).serialize())
        #self.current_player = None
        while not self.action_performed:
            self.cv.wait()

    #def __calc_real_deck_len(self):
    #    num_players = len(self.player_hands.keys())
    #    count = 5*num_players if num_players < 4 else 4*num_players
    #    for k in COLORS: count += len(self.table_cards[k])
    #    count += len(self.discard_pile)
    #    if 50 - count <= 0: self.deck_has_cards = False
    #    return max(50 - count, 0)

    def select_action(self):
        num_players = len(self.play_order) #TODO: fix play order
        thresh = 50 - (num_players-1) * (5 if num_players < 4 else 4) - 1

        deck = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])]    
        for card in self.discard_pile: deck.remove((card.color, card.value))    
        for k in COLORS:
            for card in self.table_cards[k]: deck.remove((card.color, card.value))  
        for key in self.player_hands.keys():
            if key != self.playerName:
                for card in self.player_hands[key]: deck.remove((card.color, card.value))

        hands_knowledge = [[kn.copy() for kn in self.hands_knowledge[p]] for p in self.play_order]
        table_cards = {k: [(card.color, card.value) for card in self.table_cards[k]] for k in COLORS}
        discard_pile = [(card.color, card.value) for card in self.discard_pile]
        player_hands = [[(card.color, card.value) for card in self.player_hands[p]] for p in self.play_order]
        played_last_turn = [self.played_last_turn[k] for k in self.play_order]

        env = Hanabi(num_players, verbose=True)
        env.set_state(hands_knowledge, table_cards, discard_pile, self.used_note_tokens, self.used_storm_tokens, player_hands, [], played_last_turn)

        agent = SASAgent(0, env)
        best_action = agent.act(card_thresh=35, num_simulations=1)
        
        if best_action in range(0,5): # play 0-4
            self.action_play(best_action)
        elif best_action in range(5,10): # discard 0-4
            self.action_discard(best_action - 5)
        elif best_action in range(10,10+5*(num_players-1)): # hint color to_next_player [COLORS]
            to = (self.play_order.index(self.playerName) + ((best_action - 10) // 5) + 1) % num_players
            color = COLORS[(best_action-10)%5]
            self.action_hint('color', self.play_order[to], color)
        elif best_action in range(10+5*(num_players-1),10+5*(num_players-1)*2): # hint value to_next_player 1-5
            start_val = 10+5*(num_players-1)
            to = (self.play_order.index(self.playerName) + ((best_action - start_val) // 5) + 1) % num_players
            value = ((best_action-start_val)%5)+1
            self.action_hint('value', self.play_order[to], value)

    def __abort(self):
        if self.final_score is not None:
            for c in COLORS:
                print(c[0], len(self.table_cards[c]), end=' | ')
            print()
            print(f'Final score: {self.final_score}/25')
        
        with self.lock: 
            self.run = False
            self.s.shutdown(socket.SHUT_RDWR)
        self.t_listener.join()

        exit(0)

    def main_loop(self):
        #! Check how many cards in hand (4 or 5 depending on how many players)
        with self.cv: self.action_show()
        
        len_hand = 0
        for key in self.player_hands.keys():
            if key != self.playerName:
                len_hand = len(self.player_hands[key])
                break
         
        self.hands_knowledge = {self.playerName: [['',0] for _ in range(len_hand)]}
        for player in self.player_hands.keys():
            self.hands_knowledge[player] = [['',0] for _ in range(len_hand)]
        self.played_last_turn = {k: False for k in self.player_hands.keys()}
 
        #print(self.play_order)
        #print(self.current_player)
        #print(self.player_hands)
        #print(self.hands_knowledge)
        #print(self.table_cards)
        #print(self.discard_pile)
        #print(self.used_note_tokens)
        #print(self.used_storm_tokens)
        #print(self.played_last_turn)
        #self.__abort()

        while True:

            with self.cv:

                while self.current_player != self.playerName and not self.game_ended:
                    self.cv.wait()#_for(lambda: False, 1.0)
                    if self.game_ended: self.__abort()
                    #self.check_current_player()
                
                #for p in self.player_hands:
                #    for card in self.player_hands[p]: print(p, card.color, card.value, end=' | ')
                #    print()

                self.action_show() # to obtain the current view of the game
                self.select_action()


        

if len(argv) > 1:
    ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
else:
    ID = 0
agent = TechnicAngel(ID=ID)

