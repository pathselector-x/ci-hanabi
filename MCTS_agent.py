from itertools import product
import random
import numpy as np
from hanabi import Hanabi
import time

# initial state
COLORS = ['red','yellow','green','white','blue']
VALUES = range(1,5+1)

FULL_DECK = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])] # can use .copy()
NUM_MOVES = 5
# def play_probably_safe_card(self, threshold): pass
# def discard_probably_useless_card(self, threshold): pass
# def tell_anyone_about_useful_card(self): pass
# def tell_dispensable(self): pass
# def tell_most_info(self): pass

def deepcopy(d: 'dict[str, list]'): return {key: d[key].copy() for key in d.keys()}

class Node:
    total_visits = 0

    def __init__(self, state, action=None, parent=None):
        # state:
        # player_idx, player_hands, hands_knowledge, last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck
        # player_idx is the idx of the playing player @ state
        self.player_idx, self.player_hands, self.hands_knowledge, self.last_turn_played, \
        self.table_cards, self.discard_pile, self.info_tk, self.err_tk, self.len_deck = state
        self.num_players = len(self.last_turn_played)
        self.redetermine()

        self.num_visits = 1 if parent is None else 0
        self.value = 0
        self.action = action
        self.parent = parent
        self.children = []

        self.expanded = [False for _ in range(NUM_MOVES)]
        self.valid_moves = self.__calc_valid_moves()

    def __calc_valid_moves(self):
        valid_moves = [False for _ in range(NUM_MOVES)]
        if self.err_tk == 3 or all(self.last_turn_played) or sum(len(self.table_cards[k]) for k in COLORS) == 25:
            return valid_moves
        valid_moves[0] = True
        if self.info_tk > 0:
            valid_moves[1] = True
        if self.info_tk < 8:
            valid_moves[2] = True
            valid_moves[3] = True
            valid_moves[4] = True
        return valid_moves

    def __sample_plausible_hand(self, knowledge: list, board: 'dict[str, list]', pile: list, player_hands: 'list[list]'):
        # need to build a plausible deck
        deck = FULL_DECK.copy()
        for k in COLORS:
            for card in board[k]:
                if card in deck: deck.remove(card)
        for hand in player_hands:
            for card in hand: 
                if card in deck: deck.remove(card)
        for card in pile: 
            if card in deck: deck.remove(card)

        new_kn = [] # fixes corner cases in which we can infer the card
        for c, v in knowledge:
            if c != '' and v != 0: 
                new_kn.append((c,v))
                if (c,v) in deck: deck.remove((c,v))
            elif c != '':
                count, val = 0, 0
                for k, w in deck:
                    if k == c: count += 1; val = w
                    if count > 1: break
                if count == 1: 
                    new_kn.append((c,val)); 
                    if (c,val) in deck: deck.remove((c,val))
            elif v != 0:
                count, col = 0, ''
                for k, w in deck:
                    if w == v: count += 1; col = k
                    if count > 1: break
                if count == 1: 
                    new_kn.append((col,v)) 
                    if (col,v) in deck: deck.remove((col,v))
            elif c == '' and v == 0 and len(deck) == 1: new_kn.append(deck.pop())
            else: new_kn.append((c,v))
        
        random.shuffle(deck)

        plausible_hand = []
        for c, v in new_kn:
            if c != '' and v != 0: plausible_hand.append((c,v))
            elif c != '':
                for k, w in deck:
                    if k == c: plausible_hand.append((k,w)); deck.remove((k,w)); continue
            elif v != 0:
                for k, w in deck:
                    if w == v: plausible_hand.append((k,w)); deck.remove((k,w)); continue
            else: plausible_hand.append(deck.pop())
        
        return plausible_hand, deck 
    
    def redetermine(self):
        self.hand, self.deck = self.__sample_plausible_hand(self.hands_knowledge[self.player_idx], self.table_cards, self.discard_pile, self.player_hands)
        for i in range(self.num_players):
            if i == self.player_idx: self.player_hands[i] = self.hand; break

    def play_probably_safe_card(self, threshold=0.7):
        player_hands = [card.copy() for card in self.player_hands]
        hands_knowledge = [card.copy() for card in self.hands_knowledge]
        last_turn_played = self.last_turn_played.copy()
        table_cards = deepcopy(self.table_cards)
        discard_pile = self.discard_pile.copy()
        info_tk = self.info_tk
        err_tk = self.err_tk
        len_deck = self.len_deck

        knowledge = hands_knowledge[self.player_idx]
        p = []
        for c, v in knowledge:
            if c != '' and v != 0:
                playable_val = len(table_cards[c]) + 1
                if v == playable_val: p.append(1.0)
                else: p.append(0.0)
                
            elif c != '':
                playable_val = len(table_cards[c]) + 1
                how_many = 3 if playable_val == 1 else (1 if playable_val == 5 else 2)
                total = 10

                for card in discard_pile:
                    if card[0] == c and card[1] == playable_val:
                        how_many -= 1
                    if card[0] == c: total -= 1

                for player in range(self.num_players):
                    if player != self.player_idx:
                        for card in player_hands[player]:
                            if card[0] == c and card[1] == playable_val:
                                how_many -= 1
                            if card[0] == c: total -= 1

                p.append(how_many / total)
            
            elif v != 0:
                piles_playable = [k for k in COLORS if v == len(table_cards[k]) + 1]
                how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(piles_playable)
                total = (3 if v == 1 else (1 if v == 5 else 2)) * 5

                for card in discard_pile:
                    if card[0] in piles_playable and card[1] == v:
                        how_many -= 1
                    if card[1] == v: total -= 1

                for player in range(self.num_players):
                    if player != self.player_idx:
                        for card in player_hands[player]:
                            if card[0] in piles_playable and card[1] == v:
                                how_many -= 1
                            if card[1] == v: total -= 1
                
                p.append(how_many / total)
            
            else:
                min_p = 1.0
                total = 50 - len(discard_pile) - \
                    sum(len(table_cards[k]) for k in COLORS) - \
                    sum(len(player_hands[(self.player_idx + offset) % self.num_players]) for offset in range(self.num_players-1))
                vals = {}
                for k in COLORS:
                    pv = len(table_cards[k]) + 1
                    if pv > 5: continue
                    if pv not in vals.keys(): vals[pv] = [k]
                    else: vals[pv].append(k)

                for v in vals.keys():
                    colors = vals[v]
                    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                    for card in discard_pile:
                        if card[0] in colors and card[1] == v:
                            how_many -= 1
                    for player in range(self.num_players):
                        if player != self.player_idx:
                            for card in player_hands[player]:
                                if card[0] in colors and card[1] == v:
                                    how_many -= 1
                    min_p = min(min_p, how_many / total)
                p.append(min_p)
        
        idx_to_play = np.argmax(p)
        if p[idx_to_play] >= threshold:
            # Play
            c, v = player_hands[self.player_idx].pop(idx_to_play)

            hands_knowledge[self.player_idx].pop(idx_to_play)
            if len_deck > 0:
                hands_knowledge[self.player_idx].append(('',0))
                len_deck -= 1
            else:
                last_turn_played[self.player_idx] = True

            if v == len(table_cards[c]) + 1:
                table_cards[c].append((c,v))
                if info_tk > 0: info_tk -= 1
            else:
                discard_pile.append((c,v))
                err_tk += 1

            return ((self.player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None        

    def __interrupted_pile(self, table_cards, discard_pile, color):
        for v in range(len(table_cards[color]) + 1, 6):
            count = 3 if v == 1 else (1 if v == 5 else 2)
            for card in discard_pile:
                if card[0] == color and card[1] == v:
                    count -= 1
            if count == 0: return True
        return False

    def discard_probably_useless_card(self, threshold=0.0): 
        player_hands = [card.copy() for card in self.player_hands]
        hands_knowledge = [card.copy() for card in self.hands_knowledge]
        last_turn_played = self.last_turn_played.copy()
        table_cards = deepcopy(self.table_cards)
        discard_pile = self.discard_pile.copy()
        info_tk = self.info_tk
        err_tk = self.err_tk
        len_deck = self.len_deck

        kn = hands_knowledge[self.player_idx]
        # calc prob of being useless
        p = []
        for c, v in kn:
            if c != '' and v != 0:
                if v <= len(table_cards[c]) or \
                    len(table_cards[c]) == 5 or\
                    self.__interrupted_pile(table_cards, discard_pile, c):
                    p.append(1.0)
                    continue
            elif c != '':
                if len(table_cards[c]) == 5 or\
                    self.__interrupted_pile(table_cards, discard_pile, c):
                    p.append(1.0)
                    continue
                else:
                    count = [3,2,2,2,1]
                    total = 10
                    v_lte = len(table_cards[c])
                    how_many = sum(count[:v_lte])
                    for card in discard_pile:
                        if card[0] == c and card[1] <= v_lte:
                            how_many -= 1
                        if card[0] == c: total -= 1
                    for player in range(self.num_players):
                        if player != self.player_idx:
                            for card in player_hands[player]:
                                if card[0] == c and card[1] <= v_lte:
                                    how_many -= 1
                                if card[0] == c: total -= 1
                    p.append(how_many / total)
                    continue
            elif v != 0:
                if all(v <= len(table_cards[k]) for k in COLORS):
                    p.append(1.0)
                    continue
                else:
                    total = (3 if v == 1 else (1 if v == 5 else 2)) * 5
                    colors = []
                    for k in COLORS:
                        if v == len(table_cards[k]) + 1:
                            colors.append(k)
                        
                    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                    for card in discard_pile:
                        if card[0] in colors and card[1] == v:
                            how_many -= 1
                        if card[1] == v: total -= 1
                    for player in range(self.num_players):
                        if player != self.player_idx:
                            for card in player_hands[player]:
                                if card[0] in colors and card[1] == v:
                                    how_many -= 1
                                if card[1] == v: total -= 1
                    p.append(how_many / total)
            else:
                p.append(0.0)

        idx_to_discard = np.argmax(p)
        if all(pv == p[0] for pv in p): idx_to_discard = 0
        if p[idx_to_discard] >= threshold:
            # Discard
            c, v = player_hands[self.player_idx].pop(idx_to_discard)

            hands_knowledge[self.player_idx].pop(idx_to_discard)
            if len_deck > 0:
                hands_knowledge[self.player_idx].append(('',0))
                len_deck -= 1
            else:
                last_turn_played[self.player_idx] = True

            discard_pile.append((c,v))
            info_tk -= 1

            return ((self.player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None
        
    def tell_anyone_about_useful_card(self): 
        player_hands = [card.copy() for card in self.player_hands]
        hands_knowledge = [card.copy() for card in self.hands_knowledge]
        last_turn_played = self.last_turn_played.copy()
        table_cards = deepcopy(self.table_cards)
        discard_pile = self.discard_pile.copy()
        info_tk = self.info_tk
        err_tk = self.err_tk
        len_deck = self.len_deck

        hint_type = None
        hint_val = None
        dst = None

        for pl in range(self.num_players):
            player = (self.player_idx + pl) % self.num_players
            if player != self.player_idx:
                hand = player_hands[player]
                kn = hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if len(table_cards[c]) + 1 == v:
                        if kc != '' and kv != 0: continue

                        if kc == '':
                            hint_type = 'color'
                            hint_val = c
                            dst = player
                            break
                        
                        if kv == 0:
                            hint_type = 'value'
                            hint_val = v
                            dst = player
                            break

        if hint_type is not None and hint_val is not None and dst is not None:
            info_tk += 1
            for i in range(len(player_hands[dst])):
                if player_hands[dst][i][0 if hint_type == 'color' else 1] == hint_val:
                    hands_knowledge[dst][i] = player_hands[dst][i]
            return ((self.player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None
        
    def tell_dispensable(self):
        player_hands = [card.copy() for card in self.player_hands]
        hands_knowledge = [card.copy() for card in self.hands_knowledge]
        last_turn_played = self.last_turn_played.copy()
        table_cards = deepcopy(self.table_cards)
        discard_pile = self.discard_pile.copy()
        info_tk = self.info_tk
        err_tk = self.err_tk
        len_deck = self.len_deck 

        hint_type = None
        hint_val = None
        dst = None

        for pl in range(self.num_players): 
            player = (self.player_idx + pl) % self.num_players
            if player != self.player_idx:
                hand = player_hands[player]
                kn = hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if v <= len(table_cards[c]) and kv == 0:
                        hint_type = 'value'
                        hint_val = v
                        dst = player
                        break
                    elif len(table_cards[c]) == 5 and kc == '':
                        hint_type = 'color'
                        hint_val = c
                        dst = player
                        break
                    elif self.__interrupted_pile(table_cards, discard_pile, c) and kc == '':
                        hint_type = 'color'
                        hint_val = c
                        dst = player
                        break

        if hint_type is not None and hint_val is not None and dst is not None:
            info_tk += 1
            for i in range(len(player_hands[dst])):
                if player_hands[dst][i][0 if hint_type == 'color' else 1] == hint_val:
                    hands_knowledge[dst][i] = player_hands[dst][i]
            return ((self.player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None

    def tell_most_info(self): 
        player_hands = [card.copy() for card in self.player_hands]
        hands_knowledge = [card.copy() for card in self.hands_knowledge]
        last_turn_played = self.last_turn_played.copy()
        table_cards = deepcopy(self.table_cards)
        discard_pile = self.discard_pile.copy()
        info_tk = self.info_tk
        err_tk = self.err_tk
        len_deck = self.len_deck 

        color_hints_count = [{k: 0 for k in COLORS} for _ in range(self.num_players)]
        value_hints_count = [{k: 0 for k in VALUES} for _ in range(self.num_players)]

        for player in range(self.num_players):
            if player != self.player_idx:
                hand = player_hands[player]
                kn = hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if kc == '':
                        color_hints_count[player][c] += 1
                    if kv == 0:
                        value_hints_count[player][v] += 1
        
        hint_type = None
        hint_val = None
        dst = None
        max_count = 0
        for player in range(self.num_players):
            if player != self.player_idx:
                for k in COLORS:
                    if color_hints_count[player][k] >= max_count:
                        max_count = color_hints_count[player][k]
                        hint_type = 'color'
                        hint_val = k
                        dst = player
                for v in VALUES:
                    if value_hints_count[player][v] >= max_count:
                        max_count = value_hints_count[player][v]
                        hint_type = 'value'
                        hint_val = v
                        dst = player

        if hint_type is not None and hint_val is not None and dst is not None:
            info_tk += 1
            for i in range(len(player_hands[dst])):
                if player_hands[dst][i][0 if hint_type == 'color' else 1] == hint_val:
                    hands_knowledge[dst][i] = player_hands[dst][i]
            return ((self.player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None
    
    def select(self, C=2):
        max_UCB = 0
        selected_child = None
        for child in self.children:
            UCB = (child.value / child.num_visits) + C*np.sqrt(2*np.log(Node.total_visits) / child.num_visits)
            if UCB > max_UCB or selected_child is None:
                max_UCB = UCB
                selected_child = child
        return selected_child

    def fully_expanded(self):
        return all(self.expanded)

    def expand(self):
        for i in range(len(self.valid_moves)):
            if self.expanded[i] == False and self.valid_moves[i] == True:
                next_state = None
                if i == 0: next_state = self.play_probably_safe_card(0.7)
                elif i == 1: next_state = self.discard_probably_useless_card(0.0)
                elif i == 2: next_state = self.tell_anyone_about_useful_card()
                elif i == 3: next_state = self.tell_dispensable()
                elif i == 4: next_state = self.tell_most_info()
                self.expanded[i] = True
                if next_state is not None:
                    self.children.append(Node(next_state, action=i, parent=self))
                    return
                else:
                    self.valid_moves[i] = False
                    continue
            else: self.expanded[i] = True

    def __draw(self, player_idx, player_hands, table_cards, discard_pile):
        # need to build a plausible deck
        deck = FULL_DECK.copy()
        for k in COLORS:
            for card in table_cards[k]:
                if card in deck: deck.remove(card)
        for pl in range(self.num_players):
            if pl != player_hands:
                for card in player_hands[pl]: 
                    if card in deck: deck.remove(card)
        for card in discard_pile: 
            if card in deck: deck.remove(card)
        
        random.shuffle(deck)

        player_hands[player_idx].append(deck.pop())
        
        return player_hands

    def __play_probably_safe_card(self, state, threshold):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        knowledge = hands_knowledge[player_idx]
        p = []
        for c, v in knowledge:
            if c != '' and v != 0:
                playable_val = len(table_cards[c]) + 1
                if v == playable_val: p.append(1.0)
                else: p.append(0.0)
                
            elif c != '':
                playable_val = len(table_cards[c]) + 1
                how_many = 3 if playable_val == 1 else (1 if playable_val == 5 else 2)
                total = 10

                for card in discard_pile:
                    if card[0] == c and card[1] == playable_val:
                        how_many -= 1
                    if card[0] == c: total -= 1

                for player in range(self.num_players):
                    if player != player_idx:
                        for card in player_hands[player]:
                            if card[0] == c and card[1] == playable_val:
                                how_many -= 1
                            if card[0] == c: total -= 1

                p.append(how_many / total)
            
            elif v != 0:
                piles_playable = [k for k in COLORS if v == len(table_cards[k]) + 1]
                how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(piles_playable)
                total = (3 if v == 1 else (1 if v == 5 else 2)) * 5

                for card in discard_pile:
                    if card[0] in piles_playable and card[1] == v:
                        how_many -= 1
                    if card[1] == v: total -= 1

                for player in range(self.num_players):
                    if player != player_idx:
                        for card in player_hands[player]:
                            if card[0] in piles_playable and card[1] == v:
                                how_many -= 1
                            if card[1] == v: total -= 1
                
                p.append(how_many / total)
            
            else:
                min_p = 1.0
                total = 50 - len(discard_pile) - \
                    sum(len(table_cards[k]) for k in COLORS) - \
                    sum(len(player_hands[(player_idx + offset) % self.num_players]) for offset in range(self.num_players-1))
                vals = {}
                for k in COLORS:
                    pv = len(table_cards[k]) + 1
                    if pv > 5: continue
                    if pv not in vals.keys(): vals[pv] = [k]
                    else: vals[pv].append(k)

                for v in vals.keys():
                    colors = vals[v]
                    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                    for card in discard_pile:
                        if card[0] in colors and card[1] == v:
                            how_many -= 1
                    for player in range(self.num_players):
                        if player != player_idx:
                            for card in player_hands[player]:
                                if card[0] in colors and card[1] == v:
                                    how_many -= 1
                    min_p = min(min_p, how_many / total)
                p.append(min_p)
        
        idx_to_play = np.argmax(p)
        if p[idx_to_play] >= threshold:
            # Play
            c, v = player_hands[player_idx].pop(idx_to_play)
            hands_knowledge[player_idx].pop(idx_to_play)

            if v == len(table_cards[c]) + 1:
                table_cards[c].append((c,v))
                if info_tk > 0: info_tk -= 1
            else:
                discard_pile.append((c,v))
                err_tk += 1

            if len_deck > 0:
                hands_knowledge[player_idx].append(('',0))
                len_deck -= 1
                player_hands = self.__draw(player_idx, player_hands, table_cards, discard_pile)
            else:
                last_turn_played[player_idx] = True

            return ((player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None        

    def __discard_probably_useless_card(self, state, threshold):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        kn = hands_knowledge[player_idx]
        # calc prob of being useless
        p = []
        for c, v in kn:
            if c != '' and v != 0:
                if v <= len(table_cards[c]) or \
                    len(table_cards[c]) == 5 or\
                    self.__interrupted_pile(table_cards, discard_pile, c):
                    p.append(1.0)
                    continue
            elif c != '':
                if len(table_cards[c]) == 5 or\
                    self.__interrupted_pile(table_cards, discard_pile, c):
                    p.append(1.0)
                    continue
                else:
                    count = [3,2,2,2,1]
                    total = 10
                    v_lte = len(table_cards[c])
                    how_many = sum(count[:v_lte])
                    for card in discard_pile:
                        if card[0] == c and card[1] <= v_lte:
                            how_many -= 1
                        if card[0] == c: total -= 1
                    for player in range(self.num_players):
                        if player != player_idx:
                            for card in player_hands[player]:
                                if card[0] == c and card[1] <= v_lte:
                                    how_many -= 1
                                if card[0] == c: total -= 1
                    p.append(how_many / total)
                    continue
            elif v != 0:
                if all(v <= len(table_cards[k]) for k in COLORS):
                    p.append(1.0)
                    continue
                else:
                    total = (3 if v == 1 else (1 if v == 5 else 2)) * 5
                    colors = []
                    for k in COLORS:
                        if v == len(table_cards[k]) + 1:
                            colors.append(k)
                        
                    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                    for card in discard_pile:
                        if card[0] in colors and card[1] == v:
                            how_many -= 1
                        if card[1] == v: total -= 1
                    for player in range(self.num_players):
                        if player != player_idx:
                            for card in player_hands[player]:
                                if card[0] in colors and card[1] == v:
                                    how_many -= 1
                                if card[1] == v: total -= 1
                    p.append(how_many / total)
            else:
                p.append(0.0)

        idx_to_discard = np.argmax(p)
        if all(pv == p[0] for pv in p): idx_to_discard = 0
        if p[idx_to_discard] >= threshold:
            # Discard
            c, v = player_hands[player_idx].pop(idx_to_discard)
            hands_knowledge[player_idx].pop(idx_to_discard)

            discard_pile.append((c,v))
            info_tk -= 1

            if len_deck > 0:
                hands_knowledge[player_idx].append(('',0))
                len_deck -= 1
                player_hands = self.__draw(player_idx, player_hands, table_cards, discard_pile)
            else:
                last_turn_played[player_idx] = True

            return ((player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None

    def __tell_anyone_about_useful_card(self, state):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        hint_type = None
        hint_val = None
        dst = None

        for pl in range(self.num_players):
            player = (player_idx + pl) % self.num_players
            if player != player_idx:
                hand = player_hands[player]
                kn = hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if len(table_cards[c]) + 1 == v:
                        if kc != '' and kv != 0: continue

                        if kc == '':
                            hint_type = 'color'
                            hint_val = c
                            dst = player
                            break
                        
                        if kv == 0:
                            hint_type = 'value'
                            hint_val = v
                            dst = player
                            break

        if hint_type is not None and hint_val is not None and dst is not None:
            info_tk += 1
            for i in range(len(player_hands[dst])):
                if player_hands[dst][i][0 if hint_type == 'color' else 1] == hint_val:
                    hands_knowledge[dst][i] = player_hands[dst][i]
            return ((player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None

    def __tell_dispensable(self, state):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        hint_type = None
        hint_val = None
        dst = None

        for pl in range(self.num_players): 
            player = (player_idx + pl) % self.num_players
            if player != player_idx:
                hand = player_hands[player]
                kn = hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if v <= len(table_cards[c]) and kv == 0:
                        hint_type = 'value'
                        hint_val = v
                        dst = player
                        break
                    elif len(table_cards[c]) == 5 and kc == '':
                        hint_type = 'color'
                        hint_val = c
                        dst = player
                        break
                    elif self.__interrupted_pile(table_cards, discard_pile, c) and kc == '':
                        hint_type = 'color'
                        hint_val = c
                        dst = player
                        break

        if hint_type is not None and hint_val is not None and dst is not None:
            info_tk += 1
            for i in range(len(player_hands[dst])):
                if player_hands[dst][i][0 if hint_type == 'color' else 1] == hint_val:
                    hands_knowledge[dst][i] = player_hands[dst][i]
            return ((player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None

    def __discard_oldest_first(self, state):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        # Discard
        c, v = player_hands[player_idx].pop(0)
        hands_knowledge[player_idx].pop(0)

        discard_pile.append((c,v))
        info_tk -= 1

        if len_deck > 0:
            hands_knowledge[player_idx].append(('',0))
            len_deck -= 1
            player_hands = self.__draw(player_idx, player_hands, table_cards, discard_pile)
        else:
            last_turn_played[player_idx] = True

        return ((player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
            last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)

    def __tell_randomly(self, state):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        color_hints_count = [{k: 0 for k in COLORS} for _ in range(self.num_players)]
        value_hints_count = [{k: 0 for k in VALUES} for _ in range(self.num_players)]

        for player in range(self.num_players):
            if player != player_idx:
                hand = player_hands[player]
                kn = hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if kc == '':
                        color_hints_count[player][c] += 1
                    if kv == 0:
                        value_hints_count[player][v] += 1
        
        hint_type = None
        hint_val = None
        dst = None
        max_count = 0
        for player in range(self.num_players):
            if player != player_idx:
                for k in COLORS:
                    if color_hints_count[player][k] >= max_count:
                        max_count = color_hints_count[player][k]
                        hint_type = 'color'
                        hint_val = k
                        dst = player
                for v in VALUES:
                    if value_hints_count[player][v] >= max_count:
                        max_count = value_hints_count[player][v]
                        hint_type = 'value'
                        hint_val = v
                        dst = player

        if hint_type is not None and hint_val is not None and dst is not None:
            info_tk += 1
            for i in range(len(player_hands[dst])):
                if player_hands[dst][i][0 if hint_type == 'color' else 1] == hint_val:
                    hands_knowledge[dst][i] = player_hands[dst][i]
            return ((player_idx + 1) % self.num_players, player_hands, hands_knowledge, \
                last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck)
        return None

    def __play(self, state):
        player_idx, player_hands, hands_knowledge, last_turn_played, \
        table_cards, discard_pile, info_tk, err_tk, len_deck = state

        if err_tk < 2 and len_deck == 0:
            next_state = self.__play_probably_safe_card(state, 0.0)
            if next_state is not None: return next_state

        next_state = self.__play_probably_safe_card(state, 1.0)
        if next_state is not None: return next_state

        if err_tk < 3:
            next_state = self.__play_probably_safe_card(state, 0.7)
            if next_state is not None: return next_state

        if info_tk < 8:
            next_state = self.__tell_anyone_about_useful_card(state)
            if next_state is not None: return next_state

        if info_tk > 4 and info_tk < 8:
            next_state = self.__tell_dispensable(state)
            if next_state is not None: return next_state
        
        if info_tk > 0:
            next_state = self.__discard_probably_useless_card(state, 0.0)
            if next_state is not None: return next_state
            next_state = self.__discard_oldest_first(state)
            if next_state is not None: return next_state
        else:
            next_state = self.__tell_randomly(state)
            if next_state is not None: return next_state

    def simulate(self):
        Node.total_visits += 1
        self.num_visits += 1
        player_hands = [card.copy() for card in self.player_hands]
        hands_knowledge = [card.copy() for card in self.hands_knowledge]
        last_turn_played = self.last_turn_played.copy()
        table_cards = deepcopy(self.table_cards)
        discard_pile = self.discard_pile.copy()
        info_tk = self.info_tk
        err_tk = self.err_tk
        len_deck = self.len_deck 

        done = False
        player_idx = self.player_idx
        while not done:

                player_idx, player_hands, hands_knowledge, last_turn_played, table_cards, discard_pile, \
                info_tk, err_tk, len_deck = self.__play((player_idx, player_hands, hands_knowledge, 
                    last_turn_played, table_cards, discard_pile, info_tk, err_tk, len_deck))

                if err_tk == 3 or all(last_turn_played) or sum(len(table_cards[k]) for k in COLORS) == 25:
                    done = True
                    break

        score = sum(len(table_cards[k]) for k in COLORS)
        if err_tk == 3: score = 0
        return score

    def backprop(self, node, value, num_visits):
        if node.parent is not None:
            node.parent.value += value
            node.parent.num_visits += num_visits
            node.backprop(node.parent, value, num_visits)

class MCTSAgent:
    def __init__(self, player_idx, env: Hanabi):
        self.player_idx = player_idx
        self.env = env
    
    def compute_action(self, timeout=1.0, C=2):
        state = (self.player_idx, self.env.player_hands, self.env.hands_knowledge, self.env.played_last_turn,
            self.env.table_cards, self.env.discard_pile, self.env.info_tk, self.env.err_tk, len(self.env.deck))
        root = Node(state)
        timeout = time.time() + timeout
        while time.time() <= timeout:
            root.redetermine()
            node = root

            while node.fully_expanded():
                node = node.select(C)

                if node.player_idx != root.player_idx:
                    node.redetermine()

            node.expand()
            score = node.simulate()
            node.backprop(node, score, node.num_visits)
        
        return root.select(C).action

env = Hanabi()
env.reset(0)

p1 = MCTSAgent(0, env)
print(p1.compute_action())