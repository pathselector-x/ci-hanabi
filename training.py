#import random
#import gym
#import numpy as np
#from collections import deque
#from keras.models import Sequential
#from keras.layers import Dense, LSTMCell
#from keras.optimizers import Adam
#import os
#
#### SET PARAMS
#env = gym.make('MountainCar-v0')
#state_size = env.observation_space.shape[0]
#action_size = env.action_space.n
#batch_size = 32
#n_episodes = 1001
##target_update_frequency = 50
##TODO: save directory
#
#### AGENT
#class DQNAgent:
#    def __init__(self, state_size, action_size):
#        self.state_size = state_size
#        self.action_size = action_size
#        self.memory = deque(maxlen=50000)
#        self.gamma = 0.95 # Discount factor
#        self.epsilon = 1.0 # Exploration rate of eps-greedy policy
#        self.epsilon_decay = 0.995
#        self.epsilon_min = 0.01
#        self.learning_rate = 0.001
#        self.model = self._build_model()
#
#    def _build_model(self):
#        model = Sequential()
#        model.add(Dense(24, input_dim=self.state_size, activation='relu'))
#        model.add(Dense(24, activation='relu'))
#        model.add(Dense(self.action_size, activation='linear'))
#        model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
#        return model
#
#    def remember(self, state, action, reward, next_state, done):
#        self.memory.append((state, action, reward, next_state, done))
#    
#    def act(self, state):
#        if np.random.rand() <= self.epsilon: # eps-greedy policy
#            return random.randrange(self.action_size) # act randomly i.e. explore
#        act_values = self.model.predict(state)
#        return np.argmax(act_values[0]) # we return the 'best' choice
#    
#    def replay(self, batch_size):
#        minibatch = random.sample(self.memory, batch_size)
#        for state, action, reward, next_state, done in minibatch:
#            target = reward
#            if not done:
#                target = reward + self.gamma * np.amax(self.model.predict(next_state)[0])
#            target_f = self.model.predict(state) # predicted future reward
#            target_f[0][action] = target
#            self.model.fit(state, target_f, epochs=1, verbose=0) # we want to learn to predict future reward
#        if self.epsilon > self.epsilon_min:
#            self.epsilon *= self.epsilon_decay
#    
#    def load(self, name):
#        self.model.load_weights(name)
#    
#    def save(self, name):
#        self.model.save_weights(name)
#
#agent = DQNAgent(state_size, action_size)
##target_net = DQNAgent(state_size, action_size)
##target_net.model.set_weights(online_net.model.get_weights())
#
#### INTERACT WITH ENV
#done = False
#for e in range(n_episodes):
#    state = env.reset()
#    state = np.reshape(state, [1, state_size])
#    for time in range(200): # we iterate for only some timesteps of the game (at most 200 timesteps in that game)
#        if e > 300: env.render()
#        action = agent.act(state) # action in [0,1]
#        next_state, reward, done, _ = env.step(action)
#        #reward = reward if not done else -10 # penalty since we die (it's a infinite game)
#        if next_state[1] > state[0][1] and next_state[1]>0 and state[0][1]>0:
#            reward += 15
#        elif next_state[1] < state[0][1] and next_state[1]<=0 and state[0][1]<=0:
#            reward +=15 
#        if done: reward += 10000
#        else: reward -= 10
#
#        next_state = np.reshape(next_state, [1, state_size])
#
#        agent.remember(state, action, reward, next_state, done)
#        state = next_state
#        if done:
#            print(f'Episode: {e}/{n_episodes}, Score: {reward}, eps: {agent.epsilon:.2}')
#            break
#    if len(agent.memory) > batch_size:
#        agent.replay(batch_size)
#
# https://github.com/adibyte95/Mountain_car-OpenAI-GYM/blob/master/prog.py

import random
import numpy as np
from numpy.core.defchararray import index

COLORS = ["green", "red", "blue", "yellow", "white"] 
VALUES = range(1,5+1)
PLAY_0 = 0
PLAY_1 = 1
PLAY_2 = 2
PLAY_3 = 3
PLAY_4 = 4
DISCARD_0 = 5
DISCARD_1 = 6
DISCARD_2 = 7
DISCARD_3 = 8
DISCARD_4 = 9
HINT_R = 10 # 2P
HINT_G = 11
HINT_B = 12
HINT_Y = 13
HINT_W = 14
HINT_1 = 15
HINT_2 = 16
HINT_3 = 17
HINT_4 = 18
HINT_5 = 19

class Hanabi:
    def __init__(self, num_players=2):
        assert num_players > 1 and num_players < 6, 'num_players must be 1 < num_players < 6'
        self.num_players = num_players
        self.reset()
    
    def _calc_state(self):
        deck_dict = {}
        for c in COLORS:
            deck_dict[(c,1)] = 0
            deck_dict[(c,2)] = 0
            deck_dict[(c,3)] = 0
            deck_dict[(c,4)] = 0
            deck_dict[(c,5)] = 0
        deck_state = [0 for _ in range(50)]
        for c, v in self.deck:
            deck_dict[(c,v)] += 1
        for i, c in enumerate(COLORS):
            for j, v in zip(range(10), [1,1,1,2,2,3,3,4,4,5]):
                deck_state[i * 10 + j] = 1 if deck_dict[(c,v)] > 0 else 0
                deck_dict[(c,v)] -= 1
        table_state = []
        for c in COLORS:
            table_state.append(len(self.table_cards[c]))
        hand_knowledge_state = []
        for c,v in self.players_knowledge[self.turn]:
            hand_knowledge_state.append(c)
            hand_knowledge_state.append(v)
        already_hinted_state = []
        for c,v in self.already_hinted[(self.turn + 1) % self.num_players]:
            already_hinted_state.append(c)
            already_hinted_state.append(v)
        num_cards = 5 if self.num_players < 4 else 4
        hands_state = [0 for _ in range((self.num_players-1) * num_cards * 2)]
        idxs = [n for n in range(self.turn + 1, self.num_players)]
        for i in range(self.turn): 
            idxs.append(i)
        for i, idx in enumerate(idxs):
            for j, (c,v) in enumerate(self.player_hands[idx]):
                hands_state[i * num_cards + j + 0] = COLORS.index(c) + 1
                hands_state[i * num_cards + j + 1] = v
        state = [*hand_knowledge_state, *table_state, *deck_state, 
                 *hands_state, *already_hinted_state]
        return state
        
    def reset(self):
        self.used_note_tokens = 0 # max 8
        self.used_storm_tokens = 0 # max 3
        self.discard_pile = []
        self.table_cards = {}
        self.deck = []
        for c in COLORS:
            self.deck.append((c,1)) # each card is col,val
            self.deck.append((c,1))
            self.deck.append((c,1))
            self.deck.append((c,2))
            self.deck.append((c,2))
            self.deck.append((c,3))
            self.deck.append((c,3))
            self.deck.append((c,4))
            self.deck.append((c,4))
            self.deck.append((c,5))
            self.table_cards[c] = []
        random.shuffle(self.deck)
        self.turn = 0 # max num_players-1
        self.player_hands = [[self.deck.pop() for __ in range(5 if self.num_players < 4 else 4)] for _ in range(self.num_players)]
        self.players_knowledge = [[(0,0) for __ in range(5 if self.num_players < 4 else 4)] for _ in range(self.num_players)]
        self.already_hinted = [[(0,0) for __ in range(5 if self.num_players < 4 else 4)] for _ in range(self.num_players)]

    def step(self, action): # return next_state, reward, done
        if action in [PLAY_0, PLAY_1, PLAY_2, PLAY_3, PLAY_4]:
            c,v = self.player_hands[self.turn].pop(action - PLAY_0)
            self.players_knowledge[self.turn]

            if len(self.table_cards[c]) + 1 == v:
                self.table_cards[c].append((c,v))
                self.used_note_tokens -= 1 if self.used_note_tokens > 0 else 0
            else:
                self.discard_pile.append((c,v))
                self.used_storm_tokens += 1

            self.player_hands[self.turn].append(self.deck.pop())
            self.players_knowledge[self.turn].append(self.deck.pop())
            
        elif action in [DISCARD_0, DISCARD_1, DISCARD_2, DISCARD_3, DISCARD_4]:
            card = self.player_hands[self.turn].pop(action - DISCARD_0)
            self.discard_pile.append(card)

        elif action in [HINT_R, HINT_G, HINT_B, HINT_Y, HINT_W, \
            HINT_1, HINT_2, HINT_3, HINT_4, HINT_5]:
            pass
        
        self.turn = (self.turn + 1) % self.num_players

env = Hanabi()
print(len(env._calc_state()))
