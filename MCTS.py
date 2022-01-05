from itertools import product
import random
import numpy as np
from hanabi import Hanabi
import time

COLORS = ['red','yellow','green','white','blue']
VALUES = range(1,5+1)
NUM_PLAYERS = 2

FULL_DECK = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])] # can use .copy()
def deepcopy_dict(d: 'dict[str, list]'): return {k: d[k].copy() for k in COLORS}
def deepcopy_list(l: 'list[list]'): return [c.copy() for c in l]

class State:
    def __init__(self, player_idx, player_hands, hands_knowledge, played_last_turn, table_cards, discard_pile, info_tk, err_tk, len_deck=None):
        self.player_idx = player_idx
        self.player_hands = deepcopy_list(player_hands)
        self.hands_knowledge = deepcopy_list(hands_knowledge)
        self.played_last_turn = played_last_turn.copy()
        self.table_cards = deepcopy_dict(table_cards)
        self.discard_pile = discard_pile.copy()
        self.info_tk = info_tk
        self.err_tk = err_tk
        self.len_deck = len_deck
        if self.len_deck is None: self.compute_len_deck()

    def copy(self) -> 'State':
        return State(self.player_idx, self.player_hands, self.hands_knowledge, self.played_last_turn, self.table_cards, self.discard_pile, self.info_tk, self.err_tk, self.len_deck)

    def sample_hand(self): #TODO: returns a plausible hand for the moving player @ current state
        # need to build a plausible deck
        deck = FULL_DECK.copy()
        for k in COLORS:
            for card in self.table_cards[k]: deck.remove(card)
        for pl in range(NUM_PLAYERS):
            if pl != self.player_idx:
                for card in self.player_hands[pl]: deck.remove(card)
        for card in self.discard_pile: deck.remove(card)

        new_kn = [] # fixes corner cases in which we can infer the card
        for c, v in self.hands_knowledge[self.player_idx]:
            if c != '' and v != 0: 
                new_kn.append((c,v))
                deck.remove((c,v))
            elif c != '':
                count, val = 0, 0
                for k, w in deck:
                    if k == c: count += 1; val = w
                    if count > 1: break
                if count == 1: 
                    new_kn.append((c,val))
                    deck.remove((c,val))
                else:
                    new_kn.append((c,0))
            elif v != 0:
                count, col = 0, ''
                for k, w in deck:
                    if w == v: count += 1; col = k
                    if count > 1: break
                if count == 1: 
                    new_kn.append((col,v)) 
                    deck.remove((col,v))
                else:
                    new_kn.append(('',v))
            elif c == '' and v == 0 and len(deck) == 1: new_kn.append(deck.pop())
            else: new_kn.append((c,v))
        
        random.shuffle(deck)

        plausible_hand = []
        for c, v in new_kn:
            if c != '' and v != 0: plausible_hand.append((c,v))
            elif c != '':
                for k, w in deck:
                    if k == c: plausible_hand.append((k,w)); deck.remove((k,w)); break
            elif v != 0:
                for k, w in deck:
                    if w == v: plausible_hand.append((k,w)); deck.remove((k,w)); break
            else:
                if len(deck) > 0:
                    plausible_hand.append(deck.pop())
        
        self.player_hands[self.player_idx] = plausible_hand
        self.len_deck = self.compute_len_deck() 

    def draw(self): # used when we need to reconcile a sampled hand with the move performed
        assert self.len_deck > 0
        deck = FULL_DECK.copy()
        for card in self.discard_pile:
            deck.remove(card)
        for k in COLORS:
            for card in self.table_cards[k]: deck.remove(card)
        for hand in self.player_hands:
            for card in hand: deck.remove(card)
        assert self.len_deck == len(deck)
        random.shuffle(deck)
        self.len_deck -= 1
        self.player_hands[self.player_idx].append(deck.pop())
        self.hands_knowledge[self.player_idx].append(('',0))
        self.len_deck = self.compute_len_deck()

    def pop_from_my_hand(self, num):
        card = self.player_hands[self.player_idx].pop(num)
        self.hands_knowledge[self.player_idx].pop(num)
        return card

    def is_final_state(self):
        if (self.len_deck == 0 and all(self.played_last_turn)) or \
            sum(len(self.table_cards[k]) for k in COLORS) == 25 or \
            self.err_tk == 3:
            return True
        return False
    
    def compute_len_deck(self):
        len_pile = len(self.discard_pile)
        len_hands = 0
        for p in range(NUM_PLAYERS):
            len_hands += len(self.player_hands[p])
        len_board = 0
        for k in COLORS: len_board += len(self.table_cards[k])
        return 50 - len_pile - len_hands - len_board

def interrupted_pile(state: State, color):
    for v in range(len(state.table_cards[color]) + 1, 6):
        count = 3 if v == 1 else (1 if v == 5 else 2)
        for card in state.discard_pile:
            if card[0] == color and card[1] == v:
                count -= 1
        if count == 0: return True
    return False

NUM_MOVES = 5

def play_probably_safe_card(state: State, threshold=0.7): 
    p = []
    for c, v in state.hands_knowledge[state.player_idx]:
        if c != '' and v != 0:
            playable_val = len(state.table_cards[c]) + 1
            if v == playable_val: p.append(1.0)
            else: p.append(0.0)
        elif c != '':
            playable_val = len(state.table_cards[c]) + 1
            how_many = 3 if playable_val == 1 else (1 if playable_val == 5 else 2)
            total = 10
            for card in state.discard_pile:
                if card[0] == c and card[1] == playable_val:
                    how_many -= 1
                if card[0] == c: total -= 1
            for player in range(NUM_PLAYERS):
                if player != state.player_idx:
                    for card in state.player_hands[player]:
                        if card[0] == c and card[1] == playable_val:
                            how_many -= 1
                        if card[0] == c: total -= 1
            p.append(how_many / total)
        elif v != 0:
            piles_playable = [k for k in COLORS if v == len(state.table_cards[k]) + 1]
            how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(piles_playable)
            total = (3 if v == 1 else (1 if v == 5 else 2)) * 5
            for card in state.discard_pile:
                if card[0] in piles_playable and card[1] == v:
                    how_many -= 1
                if card[1] == v: total -= 1
            for player in range(NUM_PLAYERS):
                if player != state.player_idx:
                    for card in state.player_hands[player]:
                        if card[0] in piles_playable and card[1] == v:
                            how_many -= 1
                        if card[1] == v: total -= 1
            p.append(how_many / total)
        else:
            min_p = 1.0
            total = state.len_deck + len(state.player_hands[state.player_idx])
            vals = {}
            for k in COLORS:
                pv = len(state.table_cards[k]) + 1
                if pv > 5: continue
                if pv not in vals.keys(): vals[pv] = [k]
                else: vals[pv].append(k)
            for v in vals.keys():
                colors = vals[v]
                how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                for card in state.discard_pile:
                    if card[0] in colors and card[1] == v:
                        how_many -= 1
                for player in range(NUM_PLAYERS):
                    if player != state.player_idx:
                        for card in state.player_hands[player]:
                            if card[0] in colors and card[1] == v:
                                how_many -= 1
                min_p = min(min_p, how_many / total)
            p.append(min_p)

    idx_to_play = np.argmax(p)
    if p[idx_to_play] >= threshold:
        nstate = state.copy()
        c, v = nstate.pop_from_my_hand(idx_to_play)

        if v == len(nstate.table_cards[c]) + 1:
            nstate.table_cards[c].append((c,v))
            if nstate.info_tk > 0: nstate.info_tk -= 1
        else:
            nstate.err_tk += 1
            nstate.discard_pile.append((c,v))

        if nstate.compute_len_deck() == 0:
            nstate.played_last_turn[nstate.player_idx] = True
        else:
            nstate.draw()
        
        nstate.player_idx = (nstate.player_idx + 1) % NUM_PLAYERS

        return nstate
    return None 

def discard_probably_useless_card(state: State, threshold=0.0):
    p = []
    for c, v in state.hands_knowledge[state.player_idx]:
        if c != '' and v != 0:
            if v <= len(state.table_cards[c]) or \
                len(state.table_cards[c]) == 5 or\
                interrupted_pile(state, c):
                p.append(1.0)
            else:
                p.append(0.0)
        elif c != '':
            if len(state.table_cards[c]) == 5 or\
                interrupted_pile(state, c):
                p.append(1.0)
            else:
                count = [3,2,2,2,1]
                total = 10
                v_lte = len(state.table_cards[c])
                how_many = sum(count[:v_lte])
                for card in state.discard_pile:
                    if card[0] == c and card[1] <= v_lte:
                        how_many -= 1
                    if card[0] == c: total -= 1
                for player in range(NUM_PLAYERS):
                    if player != state.player_idx:
                        for card in state.player_hands[player]:
                            if card[0] == c and card[1] <= v_lte:
                                how_many -= 1
                            if card[0] == c: total -= 1
                p.append(how_many / total)
                continue
        elif v != 0:
            if all(v <= len(state.table_cards[k]) for k in COLORS):
                p.append(1.0)
            else:
                total = (3 if v == 1 else (1 if v == 5 else 2)) * 5
                colors = []
                for k in COLORS:
                    if v == len(state.table_cards[k]) + 1:
                        colors.append(k)
                    
                how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                for card in state.discard_pile:
                    if card[0] in colors and card[1] == v:
                        how_many -= 1
                    if card[1] == v: total -= 1
                for player in range(NUM_PLAYERS):
                    if player != state.player_idx:
                        for card in state.player_hands[player]:
                            if card[0] in colors and card[1] == v:
                                how_many -= 1
                            if card[1] == v: total -= 1
                p.append(how_many / total)
        else:
            p.append(0.0)
    
    idx_to_discard = np.argmax(p)
    if all(pv == p[0] for pv in p): idx_to_discard = 0
    if p[idx_to_discard] >= threshold:
        nstate = state.copy()

        c, v = nstate.pop_from_my_hand(idx_to_discard)

        nstate.discard_pile.append((c,v))
        nstate.info_tk -= 1

        if nstate.compute_len_deck() == 0:
            nstate.played_last_turn[nstate.player_idx] = True
        else:
            nstate.draw()

        nstate.player_idx = (nstate.player_idx + 1) % NUM_PLAYERS

        return nstate
    return None

def tell_anyone_about_useful_card(state: State): 
    hint_type = None
    hint_val = None
    dst = None
    for pl in range(NUM_PLAYERS):
        player = (state.player_idx + pl) % NUM_PLAYERS
        if player != state.player_idx:
            hand = state.player_hands[player]
            kn = state.hands_knowledge[player]
            for (kc, kv), (c, v) in zip(kn, hand):
                if len(state.table_cards[c]) + 1 == v:
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
        nstate = state.copy()
        nstate.info_tk += 1

        if nstate.compute_len_deck() == 0:
            nstate.played_last_turn[nstate.player_idx] = True

        for i in range(len(nstate.player_hands[dst])):
            if hint_type == 'color' and nstate.player_hands[dst][i][0] == hint_val:
                nstate.hands_knowledge[dst][i] = (hint_val, nstate.hands_knowledge[dst][i][1])
            elif hint_type == 'value' and nstate.player_hands[dst][i][1] == hint_val:
                nstate.hands_knowledge[dst][i] = (nstate.hands_knowledge[dst][i][0], hint_val)
        nstate.player_idx = (nstate.player_idx + 1) % NUM_PLAYERS
        return nstate
    return None

def tell_dispensable(state: State):
    hint_type = None
    hint_val = None
    dst = None
    for pl in range(NUM_PLAYERS): 
        player = (state.player_idx + pl) % NUM_PLAYERS
        if player != state.player_idx:
            hand = state.player_hands[player]
            kn = state.hands_knowledge[player]
            for (kc, kv), (c, v) in zip(kn, hand):
                if v <= len(state.table_cards[c]) and kv == 0:
                    hint_type = 'value'
                    hint_val = v
                    dst = player
                    break
                elif len(state.table_cards[c]) == 5 and kc == '':
                    hint_type = 'color'
                    hint_val = c
                    dst = player
                    break
                elif interrupted_pile(state, c) and kc == '':
                    hint_type = 'color'
                    hint_val = c
                    dst = player
                    break
    if hint_type is not None and hint_val is not None and dst is not None:
        nstate = state.copy()
        nstate.info_tk += 1

        if nstate.compute_len_deck() == 0:
            nstate.played_last_turn[nstate.player_idx] = True

        for i in range(len(nstate.player_hands[dst])):
            if hint_type == 'color' and nstate.player_hands[dst][i][0] == hint_val:
                nstate.hands_knowledge[dst][i] = (hint_val, nstate.hands_knowledge[dst][i][1])
            elif hint_type == 'value' and nstate.player_hands[dst][i][1] == hint_val:
                nstate.hands_knowledge[dst][i] = (nstate.hands_knowledge[dst][i][0], hint_val)
        nstate.player_idx = (nstate.player_idx + 1) % NUM_PLAYERS
        return nstate
    return None

def tell_most_info(state: State): 
    color_hints_count = [{k: 0 for k in COLORS} for _ in range(NUM_PLAYERS)]
    value_hints_count = [{k: 0 for k in VALUES} for _ in range(NUM_PLAYERS)]
    for player in range(NUM_PLAYERS):
        if player != state.player_idx:
            hand = state.player_hands[player]
            kn = state.hands_knowledge[player]
            for (kc, kv), (c, v) in zip(kn, hand):
                if kc == '':
                    color_hints_count[player][c] += 1
                if kv == 0:
                    value_hints_count[player][v] += 1
    hint_type = None
    hint_val = None
    dst = None
    max_count = 0
    for player in range(NUM_PLAYERS):
        if player != state.player_idx:
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
        nstate = state.copy()
        nstate.info_tk += 1

        if nstate.compute_len_deck() == 0:
            nstate.played_last_turn[nstate.player_idx] = True

        for i in range(len(nstate.player_hands[dst])):
            if hint_type == 'color' and nstate.player_hands[dst][i][0] == hint_val:
                nstate.hands_knowledge[dst][i] = (hint_val, nstate.hands_knowledge[dst][i][1])
            elif hint_type == 'value' and nstate.player_hands[dst][i][1] == hint_val:
                nstate.hands_knowledge[dst][i] = (nstate.hands_knowledge[dst][i][0], hint_val)
        nstate.player_idx = (nstate.player_idx + 1) % NUM_PLAYERS
        return nstate
    return None

MOVES = [play_probably_safe_card, discard_probably_useless_card, tell_anyone_about_useful_card, tell_dispensable, tell_most_info]

class Node:
    total_visits = 0

    def __init__(self, state: State, action=None, parent=None):
        self.state = state.copy()
        self.state.sample_hand()
        self.action = action
        self.parent = parent
        self.num_visits = 0
        self.value = 0
        self.children = []

        self.to_expand = self.__valid_moves()

    #! === Expand ===
    def __valid_moves(self):
        if self.state.is_final_state(): return []
        if self.state.info_tk == 0: return [0,2,3,4]
        if self.state.info_tk == 8: return [0,1]
        return [0,1,2,3,4]

    def fully_expanded(self):
        return len(self.to_expand) == 0
    
    def expand(self):
        assert not self.fully_expanded()
        done = False
        expanded_node = None
        while not done:
            branch = self.to_expand.pop()
            next_state = MOVES[branch](self.state)
            if next_state is not None:
                expanded_node = Node(next_state, action=branch, parent=self)
                self.children.append(expanded_node)
                done = True
            if self.fully_expanded(): break
        return expanded_node
    
    #! === Select ===
    def select(self, C=2):
        max_UCB = 0
        selected_child = None
        for child in self.children:
            UCB = (child.value / child.num_visits) + C*np.sqrt(2*np.log(Node.total_visits) / child.num_visits)
            if selected_child is None or UCB > max_UCB:
                max_UCB = UCB
                selected_child = child
        return selected_child
    
    #! === Backpropagate ===
    def backprop(self, node, value, num_visits):
        if node.parent is not None:
            node.parent.value += value
            node.parent.num_visits += num_visits
            node.backprop(node.parent, value, num_visits)
    
    #! === Simulate ===
    def __play(self, state: State) -> State:
        if state.err_tk < 2 and state.len_deck == 0:
            next_state = play_probably_safe_card(state, 0.0)
            if next_state is not None: return next_state
        
        next_state = play_probably_safe_card(state, 1.0)
        if next_state is not None: return next_state

        if state.err_tk < 3:
            next_state = play_probably_safe_card(state, 0.7)
            if next_state is not None: return next_state

        if state.info_tk < 8:
            next_state = tell_anyone_about_useful_card(state)
            if next_state is not None: return next_state

        if state.info_tk > 4 and state.info_tk < 8:
            next_state = tell_dispensable(state)
            if next_state is not None: return next_state
        
        if state.info_tk > 0:
            next_state = discard_probably_useless_card(state, 0.0)
            if next_state is not None: return next_state
        else:
            next_state = tell_most_info(state)
            if next_state is not None: return next_state

    def simulate(self):
        Node.total_visits += 1
        self.num_visits += 1
        state = self.state.copy()
        while True:
            state = self.__play(state)
            if state.is_final_state(): break
        return sum(len(state.table_cards[k]) for k in COLORS) if state.err_tk < 3 else 0
        
class MCTSAgent:
    def __init__(self, player_idx, env: Hanabi):
        self.player_idx = player_idx
        self.env = env
    
    def compute_action(self, timeout=1.0, C=2):
        Node.total_visits = 0
        root = Node(State(self.player_idx, self.env.player_hands, self.env.hands_knowledge, self.env.played_last_turn, self.env.table_cards, self.env.discard_pile, self.env.info_tk, self.env.err_tk))
        timeout = time.time() + timeout
        while time.time() <= timeout:
            terminal = False
            root.state.sample_hand()
            node = root

            while node.fully_expanded():
                node = node.select(C)

                if node is None: 
                    terminal = True
                    break

                if node.state.player_idx != root.state.player_idx:
                    node.state.sample_hand()

            if terminal: continue
            
            expanded_node = node.expand()
            if expanded_node is None: continue

            score = expanded_node.simulate()
            expanded_node.backprop(expanded_node, score, expanded_node.num_visits)
        return root.select(C).action

env = Hanabi(NUM_PLAYERS)
env.reset(0)

p1 = MCTSAgent(0, env)
print(p1.compute_action(5.0))
