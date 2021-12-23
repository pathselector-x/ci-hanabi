import enum
import numpy as np
from itertools import product

def calc_playability2(hand, piles, deck):
    p = []
    for pile_col, pile_val in enumerate(piles):
        if pile_val == 5:
            p.append([0.0 for _ in range(len(hand))])
            continue
        probs = [] # of card k
        for card in hand:
            col, val = card

            if col != -1 and val != -1:
                if col == pile_col and val == pile_val + 1: probs.append(1.0)
                else: probs.append(0.0)

            elif col != -1:
                if col != pile_col: probs.append(0.0)
                total = sum([deck[(col,i)] for i in range(1,5+1)])
                probs.append(deck[(col,pile_val+1)] / total)
            
            elif val != -1:
                if val != pile_val + 1: probs.append(0.0)
                total = sum([deck[(i,val)] for i in range(5)])
                probs.append(deck[(pile_col,val)] / total)
            
            else:
                total = sum([deck[(i,j)] for i,j in product(range(5), range(1,5+1))])
                probs.append(deck[(pile_col,pile_val+1)] / total)

        p.append(np.asarray(probs))
    
    p = np.asarray(p)
    
    return p

def p_val_given_col(val, col, deck):
    # p(val|col) of a card
    total = sum(deck[(col,i)] for i in range(1,5+1))
    return deck[(col,val)] / total

def p_col_given_val(val, cols, deck):
    # p(col|val) of a card
    total = sum(deck[(i,val)] for i in range(5))
    return sum(deck[(col,val)] for col in cols) / total

def calc_playability(hand, piles, deck):
    playabilities = []
    for card in hand:
        c, v = card
        p = []
        if c != -1 and v != -1: # I know both col and val
            for pc, pv in enumerate(piles):
                if c == pc and v == pv + 1: p.append(1.0)
                else: p.append(0.0)

        elif c != -1: # I know only the col
            for pc, pv in enumerate(piles):
                if pv == 5: p.append(0.0)
                elif c == pc: p.append(deck[(c,pv+1)] / sum(deck[(c,i)] for i in range(1,5+1)))
                else: p.append(0.0)
        
        elif v != -1: # I know only the val
            for pc, pv in enumerate(piles):
                if pv == 5: p.append(0.0)
                elif v == pv + 1: p.append(sum(deck[(i,v)] for i in range(5) if piles[i] + 1 == v) / sum(deck[(i,v)] for i in range(5)))
                else: p.append(0.0)
            
        else: # I don't know anything
            for pc, pv in enumerate(piles):
                if pv == 5: p.append(0.0)
                else: p.append(deck[(pc,pv+1)] / sum(deck[(i,j)] for i,j in product(range(5), range(1,5+1))))

        playabilities.append(p)
                
    playabilities = np.asarray(playabilities)
    playabilities = np.max(playabilities, axis=1)
    return playabilities



deck = {}
for col in range(5): # num cards with that (col,val) in deck
    deck[(col,1)] = 3
    deck[(col,2)] = 2
    deck[(col,3)] = 2
    deck[(col,4)] = 2
    deck[(col,5)] = 1

# col,val
hand = [
    (-1,-1),
    (-1,-1),
    (-1,1),
    (-1,-1),
    (-1,-1),
]

# R,G,B,Y,W
piles = [0,0,0,0,0]

for card in hand:
    c, v = card
    if c != -1 and v != -1:
        deck[card] -= 1

for c,v in enumerate(piles):
    for i in range(1,v+1):
        deck[(c,i)] -= 1

print(calc_playability(hand, piles, deck))