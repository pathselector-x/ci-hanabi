import itertools
import os
from typing import Sequence
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import random
from sys import argv, stdout
from threading import Thread, Lock, Condition

from keras.engine.training import Model
import GameData
import socket
from constants import *
import numpy as np
from collections import deque
from itertools import count, product

import pickle

from game import Card, Player

COLORS = ['red','yellow','green','blue','white']
VALUES = range(1,5+1)

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

        self.position = None #! To know the order of who plays and when
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
        #input('Press [ENTER] to start...')
        #time.sleep(3)
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
        if self.s is not None:
            self.s.close()

    def listener(self):
        try:
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

                        if type(data) is not GameData.ServerGameStateData:
                            with self.cv: self.cv.notify_all()

        except ConnectionResetError: 
            with self.lock: self.game_ended = True
            with self.cv: self.cv.notify_all()
                
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
                        self.current_hand_knowledge[i][0 if data.type == 'color' else 1] = str(data.value)
                    read_pkts.append(data)

                # Hint data of other players
                elif type(data) is GameData.ServerHintData and data.destination != self.playerName:
                    for i in data.positions: # indices in the current hand
                        self.already_hinted[data.destination][i][0 if data.type == 'color' else 1] = True
                    read_pkts.append(data)
                
                # Game over
                elif type(data) is GameData.ServerGameOver:
                    self.game_ended = True
                    self.final_score = data.score
                    read_pkts.append(data)
                
                elif type(data) is not GameData.ServerGameStateData:
                    read_pkts.append(data)

            for pkt in read_pkts:
                self.msg_queue.remove(pkt)

    def wait_for_turn(self):
        while self.current_player != self.playerName and not self.game_ended:
            with self.cv: self.cv.wait_for(lambda : False, timeout=0.1)
            self.consume_packets()
            if not self.game_ended: self.action_show()
        self.consume_packets()
        if not self.game_ended: self.action_show()
    
    def action_show(self):
        try: self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
        except ConnectionResetError: return
        found = False
        while not found:
            with self.lock:
                if self.game_ended: return
                read_pkts = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerGameStateData:
                        self.current_player = str(data.currentPlayer)
                        self.player_hands = []
                        for player in data.players:
                            pl = Player(player.name)
                            for card in player.hand:
                                pl.hand.append(Card(card.id, card.value, card.color))
                            self.player_hands.append(pl)
                        self.table_cards = { "red": [], "yellow": [], "green": [], "blue": [], "white": [] }
                        for k in data.tableCards.keys():
                            for card in data.tableCards[k]:
                                self.table_cards[k].append(Card(card.id, card.value, card.color))
                        self.discard_pile = []
                        for card in data.discardPile:
                            self.discard_pile.append(Card(card.id, card.value, card.color))
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
    
    def action_play(self, num):
        print('Play', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Play'
        assert num in range(0, len(self.current_hand_knowledge))
        self.s.send(GameData.ClientPlayerPlayCardRequest(self.playerName, num).serialize())
        self.current_hand_knowledge.pop(num)
        self.current_hand_knowledge.append(['', ''])
        self.current_player = None
    
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

    def select_action(self): #! WE JUST CONSIDER 2 PLAYERS!!!
        pass
            
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
            if self.game_ended: break
            self.select_action()

        if self.final_score is not None:
            for c in COLORS:
                print(c[0], len(self.table_cards[c]), end=' | ')
            print()
            print(f'Final score: {self.final_score}/25')

#ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
#agent = TechnicAngel(ID=ID)

#https://ai.facebook.com/blog/building-ai-that-can-master-complex-cooperative-games-with-hidden-information/
#https://helios2.mi.parisdescartes.fr/~bouzy/publications/bouzy-hanabi-2017.pdf

import random

class Hanabi:
    def __init__(self, view_colors=['red','white','green','blue','yellow']):
        self.num_actions = 20 # P0-4, D0-4, HCR-W, HV1-5
        self.num_players = 2
        self.hand_size = 5
        self.state_size = 86
        self.view_colors = view_colors
        #self.reset()

    def __interrupted_pile(self, color):
        val_to_test = len(self.table_cards[color]) + 1
        max_count = 2 if val_to_test in [2,3,4] else (3 if val_to_test == 1 else 1)
        count = 0
        for c, v in self.discard_pile:
            if c == color and v == val_to_test:
                count += 1
        if count == max_count: # all have been discarded, we can't cont. the pile
            return True
        return False
    
    def __one_copy_left(self, color, value):
        max_count = 2 if value in [2,3,4] else (3 if value == 1 else 1)
        count = 0
        for c, v in self.discard_pile:
            if c == color and v == value:
                count += 1
        if max_count - count == 1:
            return True
        return False

    def compute_state(self, player_idx, permute_colors=False): # state is just a belief
        self.state = [0 for _ in range(50)]
        if permute_colors:
            for c, v in self.deck:
                self.state[self.view_colors.index(c) * 5 + v - 1] = 1
        else:
            for c, v in self.deck:
                self.state[COLORS.index(c) * 5 + v - 1] = 1
        if len(self.state) < 50: print('ERROR in deck')
        for c, v in self.hands_knowledge[player_idx]:
            if c != '' and v != 0:
                if permute_colors:
                    self.state.append(self.view_colors.index(c))
                else:
                    self.state.append(COLORS.index(c))
                self.state.append(v)
            elif c != '':
                if permute_colors:
                    self.state.append(self.view_colors.index(c))
                else:
                    self.state.append(COLORS.index(c))
                self.state.append(v)
            elif v != 0:
                self.state.append(0)
                self.state.append(v)
            else:
                self.state.append(0)
                self.state.append(0)
        if len(self.state) < 60: print('ERROR in my kn')
        for p_idx in list(set(range(self.num_players))-set([player_idx])):
            for c, v in self.hands_knowledge[p_idx]:
                if c != '' and v != 0:
                    if permute_colors:
                        self.state.append(self.view_colors.index(c))
                    else:
                        self.state.append(COLORS.index(c))
                    self.state.append(v)
                elif c != '':
                    if permute_colors:
                        self.state.append(self.view_colors.index(c))
                    else:
                        self.state.append(COLORS.index(c))
                    self.state.append(v)
                elif v != 0:
                    self.state.append(0)
                    self.state.append(v)
                else:
                    self.state.append(0)
                    self.state.append(0)
        if len(self.state) < 70: print('ERROR in op kn')
        for p_idx in list(set(range(self.num_players))-set([player_idx])):
            for c, v in self.player_hands[p_idx]:
                if permute_colors:
                    self.state.append(self.view_colors.index(c))
                else:
                    self.state.append(COLORS.index(c))
                self.state.append(v)
            if len(self.player_hands[p_idx]) < 5: #TODO: solve bug
                self.state.append(0)
                self.state.append(0)
        if len(self.state) < 80: print('ERROR in op hand')
        if permute_colors:
            for k in self.view_colors:
                self.state.append(len(self.table_cards[k])) 
        else:
            for k in COLORS:
                self.state.append(len(self.table_cards[k]))
        if len(self.state) < 85: print('ERROR in table')
        self.state.append(self.info_tk)
        return np.array(self.state)

    def is_valid(self, action):
        if action in range(0,5): # play 0-4
            return True
        elif action in range(5,10): # discard 0-4
            if self.info_tk == 0: return False
            return True
        elif action in range(10,20): # hint
            if self.info_tk == 8: return False
            return True
        
    def reset(self, player_idx, permute_colors=False):
        self.info_tk = 0 # max 8
        self.err_tk = 0 # max 3
        self.last_turn = False
        self.deck = []
        for c in COLORS:
            self.deck.append((c,1))
            self.deck.append((c,1))
            self.deck.append((c,1))
            self.deck.append((c,2))
            self.deck.append((c,2))
            self.deck.append((c,3))
            self.deck.append((c,3))
            self.deck.append((c,4))
            self.deck.append((c,4))
            self.deck.append((c,5))
        random.shuffle(self.deck)
        self.table_cards = {k: [] for k in COLORS}
        self.discard_pile = []
        self.player_hands = [[self.deck.pop() for __ in range(self.hand_size)] for _ in range(self.num_players)]
        self.hands_knowledge = [[['',0] for __ in range(self.hand_size)] for _ in range(self.num_players)]
        self.played_last_turn = [False for _ in range(self.num_players)]
        return self.compute_state(player_idx, permute_colors)
    
    def __action_play(self, player_idx, num):
        done = False
        reward = 0

        self.hands_knowledge[player_idx].pop(num)
        self.hands_knowledge[player_idx].append(['',0])

        c, v = self.player_hands[player_idx].pop(num)
        if len(self.deck) > 0: self.player_hands[player_idx].append(self.deck.pop())
        else: self.last_turn = True
        if self.last_turn: self.played_last_turn[player_idx] = True

        if v == len(self.table_cards[c]) + 1:
            self.table_cards[c].append((c,v))
            reward = 5 + v
            if self.info_tk > 0: 
                self.info_tk -= 1
            if all(len(self.table_cards[k]) == 5 for k in COLORS):
                reward = 100
                done = True
            return reward, done # reward
        else:
            self.discard_pile.append((c,v))
            self.err_tk += 1
            reward = -33
            if self.err_tk == 3:
                reward = -100
                done = True
            return reward, done
    
    def __action_discard(self, player_idx, num):
        done = False
        reward = 0

        self.hands_knowledge[player_idx].pop(num)
        self.hands_knowledge[player_idx].append(['',0])

        c, v = self.player_hands[player_idx].pop(num)
        if len(self.deck) > 0: self.player_hands[player_idx].append(self.deck.pop())
        else: self.last_turn = True
        if self.last_turn: self.played_last_turn[player_idx] = True

        self.discard_pile.append((c,v))
        self.info_tk -= 1

        if v <= len(self.table_cards[c]) or self.__interrupted_pile(c): # useless
            reward = 5
        else:
            max_count = 2 if v in [2,3,4] else (3 if v == 1 else 1)
            count = 0
            for card in self.discard_pile:
                if card[0] == c and card[1] == v:
                    count += 1
            if count == max_count: reward = 6 - v # i've interrupted a pile
            else: reward = 1

        return reward, done

    def __action_hint(self, player_idx, type, to, value):
        reward = 0
        self.info_tk += 1

        prev_kn = [['',0] for _ in range(self.hand_size)]
        for i, card in enumerate(self.hands_knowledge[to]):
            prev_kn[i][0] = card[0]
            prev_kn[i][1] = card[1]

        for i, card in enumerate(self.player_hands[to]):
            if card[0 if type == 'color' else 1] == value:
                self.hands_knowledge[to][i][0 if type == 'color' else 1] = value
        if self.last_turn: self.played_last_turn[player_idx] = True

        already_hinted = True
        for prev, new in zip(prev_kn, self.hands_knowledge[to]):
            if prev[0] != new[0] or prev[1] != new[1]:
                already_hinted = False
                break
        if already_hinted: reward = -33
        else:
            reward = 1
            idx = 0
            for prev, new in zip(prev_kn, self.hands_knowledge[to]):
                if prev[1] != new[1] and \
                    self.hands_knowledge[to][idx][0] != '' and \
                    self.player_hands[to][idx][1] == len(self.table_cards[self.hands_knowledge[to][idx][0]]) + 1: # directly playable
                    reward = 5
                    break
                elif prev[1] != new[1] and \
                    all(self.player_hands[to][idx][1] == len(self.table_cards[k]) + 1 for k in COLORS): # directly playable
                    reward = 5
                    break
                idx += 1
            idx = 0
            for prev, new in zip(prev_kn, self.hands_knowledge[to]):
                if prev[1] != new[1] and \
                    self.hands_knowledge[to][idx][0] != '' and \
                    self.player_hands[to][idx][1] <= len(self.table_cards[self.hands_knowledge[to][idx][0]]): # directly discardable
                    reward = 5
                    break
                elif prev[1] != new[1] and \
                    all(self.player_hands[to][idx][1] <= len(self.table_cards[k]) for k in COLORS): # directly discardable
                    reward = 5
                    break
                idx += 1

        return reward, False
        
    def step(self, player_idx, action, permute_colors=False):
        if action in range(0,5): # play 0-4
            reward, done = self.__action_play(player_idx, action)
        elif action in range(5,10): # discard 0-4
            reward, done = self.__action_discard(player_idx, action - 5)
        elif action in range(10,15): # hint color to_next_player [COLORS]
            reward, done = self.__action_hint(player_idx, 'color', (player_idx + 1) % self.num_players, COLORS[action - 10])
        elif action in range(15,20): # hint value to_next_player 1-5
            reward, done = self.__action_hint(player_idx, 'value', (player_idx + 1) % self.num_players, action - 14)

        next_state = self.compute_state(player_idx, permute_colors)

        if all(self.played_last_turn): done = True

        return next_state, reward, done, None

import time
import keras
from keras.models import Model, Sequential
from keras.layers import Dense, LSTM
from keras.optimizers import Adam

class Agent:
    def __init__(self, player_idx, env):
        self.player_idx = player_idx
        self.env = env

        self.lr = 0.001
        self.gamma = 0.9
        self.sequence_length = 10
        self.overlap_length = 5
        self.batch_size = 32
        self.maxlen = 20000
        self.memory = []
        self.epsilon = 1.0
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.2
        self.target_update_freq = 100

        self.online_net = self.__build_model(self.env.state_size, self.env.num_actions)
        self.target_net = self.__build_model(self.env.state_size, self.env.num_actions)
        
        if os.path.exists('./models/online_net_' + str(player_idx)):
            self.online_net.load_weights('./models/online_net_' + str(player_idx))
        if os.path.exists('./models/target_net_' + str(player_idx)):
            self.target_net.load_weights('./models/target_net_' + str(player_idx))
        else:
            self.target_net.set_weights(self.online_net.get_weights())
    
    def __build_model(self, input_shape, output_shape):
        inputs = keras.Input(shape=(self.sequence_length, input_shape))
        x = Dense(32, activation='relu')(inputs)
        x = Dense(64, activation='relu')(x)
        x = Dense(64, activation='relu')(x)
        x = LSTM(512)(x)
        outputs = Dense(output_shape, activation='linear')(x)
        model = Model(inputs=inputs, outputs=outputs, name='technic_angel')
        model.compile(loss='mse', optimizer=Adam(learning_rate=self.lr))
        #model.summary()
        return model

    def remember(self, state, action, reward, done):
        mem_len = len(self.memory)
        if mem_len > 0:
            last_len = len(self.memory[-1])
            if last_len < self.sequence_length:
                self.memory[-1].append((state, action, reward, done))
            else:
                self.memory.append([])
                cnt = self.overlap_length
                while len(self.memory[-1]) < self.overlap_length:
                    self.memory[-1].append(self.memory[-2][cnt])
                    cnt += 1
        else:
            self.memory.append([(state, action, reward, done)])
        if done:
            while len(self.memory[-1]) < self.sequence_length:
                self.memory[-1].append((state, action, reward, done))
        while len(self.memory) > self.maxlen:
            self.memory.pop(0)
    
    def act(self, state, model=None):
        action = None
        state = np.reshape(state, [1, self.env.state_size])
        state = np.concatenate([np.zeros((9,self.env.state_size)), state])
        while action is None or not self.env.is_valid(action):
            if random.random() <= self.epsilon:
                action = random.choice(range(self.env.num_actions))
            else:
                if model is None:
                    act_values = self.online_net.predict(state[np.newaxis, :, :])
                    action = np.argmax(act_values[0])
                else: # Test
                    act_values = model.predict(state[np.newaxis, :, :])
                    action = np.argmax(act_values[0])
                    if not self.env.is_valid(action):
                        action = random.choice(range(self.env.num_actions))
        return action

    def replay(self):
        seq_idx = random.choice(range(len(self.memory)-2))
        seq = self.memory.pop(seq_idx)
        next_seq = self.memory.pop(seq_idx)

        states = []
        rewards = 0
        actions = None
        dones = True
        next_states = []
        for state, action, reward, done in seq:
            dones = dones and done
            if actions is None: actions = action
            states.append(np.reshape(state, [1, state.size]))
            rewards += reward
        
        states = np.concatenate(states)

        for next_state, _, _, _ in next_seq:
            next_states.append(np.reshape(next_state, [1, next_state.size]))

        next_states = np.concatenate(next_states)

        target = rewards
        if not dones:
            target = reward + self.gamma * np.amax(self.target_net.predict(next_states[np.newaxis, :, :])[0])
        target_f = self.online_net.predict(states[np.newaxis, :, :])
        target_f[0][action] = target
        self.online_net.fit(states[np.newaxis, :, :], target_f, epochs=1, verbose=0)
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

def swap_randomly(L):
    new_L = L.copy()
    idx1, idx2 = None, None
    while (idx1 is None or idx2 is None) and (idx1 == idx2):
        idx1 = random.choice(range(len(L)))
        idx2 = random.choice(range(len(L)))
    tmp = new_L[idx1]
    new_L[idx1] = new_L[idx2]
    new_L[idx2] = tmp
    return new_L

NUM_EPISODES = 10000
SAVE_FREQ = 100
PRINT_EVERY = 100

env = Hanabi()
p1 = Agent(0, env)
p2 = Agent(1, env)

def test():
    p1.epsilon = 0
    p2.epsilon = 0
    done = False
    state = env.reset(0)
    while not done:
        action = p1.act(state, model=p1.target_net)
        if action in range(5):
            print(f'P1 Play {env.player_hands[0][action]}')
        elif action in range(5,10):
            print(f'P1 Discard {env.player_hands[0][action - 5]}')
        elif action in range(10,15):
            print(f'P1 Hint "color" P2 {COLORS[action - 10]}')
        elif action in range(15,20):
            print(f'P1 Hint "value" P2 {action - 14}')
        next_state, reward, done, _ = env.step(0, action)
        if done: break

        state = env.compute_state(1)
        action = p1.act(state, model=p1.target_net)
        if action in range(5):
            print(f'P2 Play {env.player_hands[1][action]}')
        elif action in range(5,10):
            print(f'P2 Discard {env.player_hands[1][action - 5]}')
        elif action in range(10,15):
            print(f'P2 Hint "color" P1 {COLORS[action - 10]}')
        elif action in range(15,20):
            print(f'P2 Hint "value" P1 {action - 14}')
        next_state, reward, done, _ = env.step(1, action)
        if done: break
        state = env.compute_state(0)

    print(f'Error tokens: {env.err_tk}, Info tokens: {env.info_tk}')
    for k in COLORS:
        print(f'{k}: {len(env.table_cards[k])} |', end=' ')
    exit()

#test()
avg_len = 0
avg_rew = 0

start_wt = time.time()

for e in range(NUM_EPISODES):

    env.view_colors = swap_randomly(COLORS)
    state = env.reset(0) # P1 always goes first

    episode_reward = 0
    
    for t in itertools.count(): # timesteps of episode
        # P1
        action = p1.act(state)
        next_state, reward, done, _ = env.step(0, action)
        episode_reward += reward
        p1.remember(state, action, reward, done)
        if done:
            avg_len += t
            avg_rew += episode_reward
            break

        # P2
        state = env.compute_state(1, permute_colors=True)
        action = p2.act(state)
        next_state, reward, done, _ = env.step(1, action, permute_colors=True)
        episode_reward += reward
        p2.remember(state, action, reward, done)
        if done:
            avg_len += t
            avg_rew += episode_reward
            break
        state = env.compute_state(0, permute_colors=False)
    
    if len(p1.memory) > 4:
        p1.replay()
    
    if e % p1.target_update_freq == 1:
        p1.target_net.set_weights(p1.online_net.get_weights())
    
    if len(p2.memory) > 4:
        p2.replay()
    
    if e % p2.target_update_freq == 1:
        p2.target_net.set_weights(p2.online_net.get_weights())
    
    if e % SAVE_FREQ == 1:
        p1.online_net.save_weights('./models/online_net_0')
        p1.target_net.save_weights('./models/target_net_0')
        p2.online_net.save_weights('./models/online_net_1')
        p2.target_net.save_weights('./models/target_net_1')
    
    if e % PRINT_EVERY == 0:
        stop_wt = time.time()
        print(f'\n# Episode {e} | in {(stop_wt - start_wt):.2f}s #')
        start_wt = stop_wt
        print(f'Error tokens: {env.err_tk}, Info tokens: {env.info_tk}')
        for k in COLORS:
            print(f'{k}: {len(env.table_cards[k])} |', end=' ')
        print()
        print(f'Average Length of episodes: {2 * avg_len / PRINT_EVERY}')
        print(f'Average Reward of episodes: {avg_rew / (2 * PRINT_EVERY)}')
        print(f'Episode reward: {episode_reward}')
        avg_len = 0
        avg_rew = 0
