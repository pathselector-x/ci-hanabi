from sys import argv, stdout
from threading import Thread, Lock, Condition
from itertools import product
import random
import numpy as np

import GameData
import socket
from constants import *

from game import Card

from hanabi import Hanabi
from single_agent_search import SASAgent

COLORS = ['red','yellow','green','blue','white']
VALUES = range(1,5+1)

num_players = 4
thresh = 50 - num_players * (5 if num_players < 4 else 4) - 1
print(thresh)
deck = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])]
random.shuffle(deck)
hands_knowledge = [[['',0] for _ in range(5 if num_players < 4 else 4)] for _ in range(num_players)]
table_cards = {k: [] for k in COLORS}
discard_pile = []
if num_players < 4:
    player_hands = [[deck.pop(), deck.pop(), deck.pop(), deck.pop(), deck.pop()] for _ in range(num_players)]
else:
    player_hands = [[deck.pop(), deck.pop(), deck.pop(), deck.pop()] for _ in range(num_players)]

env = Hanabi(num_players, verbose=True)
env.set_state(hands_knowledge, table_cards, discard_pile, 0, 0, player_hands, deck, [False for _ in range(num_players)])

players = []
for i in range(num_players):
    players.append(SASAgent(i, env))

done = env.is_final_state()
while not done:
    for a in players:
        best_action = a.act(card_thresh=thresh)
        if env.is_final_state(): 
            done = True
            break

print('Final score: ', env.final_score())