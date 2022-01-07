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

deck = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])]
random.shuffle(deck)
hands_knowledge = [[['',0] for _ in range(5)] for _ in range(2)]
table_cards = {k: [] for k in COLORS}
discard_pile = []
player_hands = [
    [deck.pop(), deck.pop(), deck.pop(), deck.pop(), deck.pop()], 
    [deck.pop(), deck.pop(), deck.pop(), deck.pop(), deck.pop()]
]

env = Hanabi(2)
env.set_state(hands_knowledge, table_cards, discard_pile, 0, 0, player_hands, deck, [False, False])

p1 = SASAgent(0, env)
p2 = SASAgent(1, env)

done = env.is_final_state()
while not done:
    print(p1.act(card_thresh=100))
    if env.is_final_state(): break
    print(p2.act(card_thresh=100))
    if env.is_final_state(): break
print(env.final_score())