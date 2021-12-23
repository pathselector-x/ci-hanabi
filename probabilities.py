import numpy as np
from itertools import product
import random

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
    return playabilities # Each value will be the playability of each single card e.g. [0.06, 0.06, 1.0, 0.06, 0.06]

def calc_discardability(hand, piles, deck):
    discardabilites = []
    for card in hand:
        c, v = card
        p = []
        if c != -1 and v != -1:
            for pc, pv in enumerate(piles):
                pass

def calc_best_hint(players, piles, deck):
    # players: order based who is after I played (.hand, .name, .hints)
    # hinted: [[(True,False)...(False,False)], [...], [...] ... ] # col, val hints
    best_so_far = (players[0].name, 'v', 1, 0.0) # dst, type, val, playability/utility
    for player in players:
        color_hints = [0,1,2,3,4]
        value_hints = [1,2,3,4,5]
        for card, hint in zip(player.hand, player.hints):
            c, v = card
            hc, hv = hint
            if hc: color_hints.remove(c)
            if hv: value_hints.remove(v)
        
        if len(color_hints) > 0 or len(value_hints) > 0: # at least one useful hint found to deliver
            for vhint in value_hints:
                simulate_hand = []
                simulate_hints = []
                for hint in player.hints:
                    simulate_hints.append(hint)
                for i, card in enumerate(player.hand):
                    if card[1] == vhint: simulate_hints[i][1] = True

                for card, hint in zip(player.hand, simulate_hints):
                    c, v = -1, -1
                    hc, hv = hint
                    if hc: c = card[0]
                    if hv: v = card[1]
                    simulate_hand.append((c,v))

                utility = np.max(calc_playability(simulate_hand, piles, deck))
                if utility > best_so_far[3]:
                    best_so_far = (player.name, 'v', vhint, utility)
                    if utility == 1.0: return best_so_far

            for chint in color_hints:
                simulate_hand = []
                simulate_hints = []
                for hint in player.hints:
                    simulate_hints.append(hint)
                for i, card in enumerate(player.hand):
                    if card[0] == chint: simulate_hints[i][0] = True

                for card, hint in zip(player.hand, simulate_hints):
                    c, v = -1, -1
                    hc, hv = hint
                    if hc: c = card[0]
                    if hv: v = card[1]
                    simulate_hand.append((c,v))

                utility = np.max(calc_playability(simulate_hand, piles, deck))
                if utility > best_so_far[3]:
                    best_so_far = (player.name, 'c', chint, utility)
                    if utility == 1.0: return best_so_far

            return best_so_far
    
    return best_so_far

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