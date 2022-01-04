from itertools import product
import random
from hanabi import COLORS, VALUES, deepcopy, Hanabi
import numpy as np
import time

# initial state
FULL_DECK = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])] # can use .copy()

class Node:
    total_visits = 0

    def __init__(self, player_idx, hands_knowledge, board, pile, player_hands, info_tk, err_tk, num_players, action=None, value=0, parent=None):
        self.env = Hanabi(num_players)
        self.player_idx = player_idx
        self.__info_tk = info_tk
        self.__err_tk = err_tk
        self.__hands_knowledge = [hands_knowledge[i].copy() for i in range(self.env.num_players)]
        self.__board = deepcopy(board)
        self.__pile = pile.copy()
        self.__player_hands = [player_hands[i].copy() for i in range(self.env.num_players)]
        self.redetermine()

        self.num_visits = 0
        self.action = action
        self.value = value
        self.parent = parent
        self.children = []
        self.expanded = [False, False, False, False, False]
        self.valid_moves = self.__valid_moves()

    def __sample_plausible_hand(self, knowledge: list, board: 'dict[str, list]', pile: list, player_hands: 'list[list]'):
        # need to build a plausible deck
        deck = FULL_DECK.copy()
        for k in knowledge.keys():
            for card in board: deck.remove(card)
        for hand in player_hands:
            for card in hand: deck.remove(card)
        for card in pile: deck.remove(card)

        new_kn = [] # fixes corner cases in which we can infer the card
        for c, v in knowledge:
            if c != '' and v != 0: new_kn.append((c,v)); deck.remove((c,v))
            elif c != '':
                count, val = 0, 0
                for k, w in deck:
                    if k == c: count += 1; val = w
                    if count > 1: break
                if count == 1: new_kn.append((c,val)); deck.remove((c,val))
            elif v != 0:
                count, col = 0, ''
                for k, w in deck:
                    if w == v: count += 1; col = k
                    if count > 1: break
                if count == 1: new_kn.append((col,v)); deck.remove((col,v))
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
        self.hand, self.deck = self.__sample_plausible_hand(self.__hands_knowledge[self.player_idx], self.__board, self.__pile, self.__player_hands)
        for i in range(self.env.num_players):
            if i == self.player_idx: self.__player_hands[i] = self.hand
        self.env.set_state(self.__hands_knowledge, self.__board, self.__pile, self.__info_tk, self.__err_tk, self.__player_hands, self.deck)

    def __default_policy(self, player): # used in simulation #TODO
        if self.env.err_tk < 2 and len(self.env.deck) == 0:
            if self.__play_probably_safe_card(0.0): return
        
        if self.__play_safe_card(): return

        if self.env.err_tk < 3:
            if self.__play_probably_safe_card(0.7): return

        if self.env.info_tk < 8:
            if self.__tell_anyone_about_useful_card(): return

        if self.env.info_tk > 4 and self.env.info_tk < 8:
            if self.__tell_dispensable(): return
        
        if self.env.info_tk > 0:
            if self.__osawa_discard(): return
            if self.__discard_probably_useless_card(0.0): return
            if self.__discard_oldest_first(): return
        else:
            if self.__tell_randomly(): return
    
    def play_probably_safe_card(self, player, threshold=0.7):pass
    def discard_probably_useless_card(self, player, threshold=0.0):pass
    def tell_anyone_about_useful_card(self, player): pass
    def tell_dispensable(self, player): pass
    def tell_most_info(self, player): pass

    def remove_and_determine_incompatible_cards(self): pass
    
    def __valid_moves(self):
        actions = [False, False, False, False, False] # play_prob_safe, ...
        if self.env.err_tk == 3 or all(self.env.played_last_turn) or sum(len(self.env.table_cards[k]) for k in COLORS): return actions
        
        actions[0] = True  # play_probably_safe_card
        if self.env.info_tk > 0:
            actions[1] = True # discard_probably_useless_card
        if self.env.info_tk < 8:
            actions[2] = True # tell_anyone_about_useful_card
            actions[3] = True # tell_dispensable
            actions[4] = True # tell_most_info
        return actions
    
    def fully_expanded(self):
        return all(self.expanded)

    def simulate(self):
        Node.total_visits += 1
        self.num_visits += 1
        done = False
        while not done:
            for pl in range(self.env.num_players):
                player = (self.player_idx + pl) % self.env.num_players
                self.__default_policy(player)
                if self.env.err_tk == 3 or all(self.env.played_last_turn) or sum(len(self.env.table_cards[k]) for k in COLORS) == 25:
                    done = True
                    break
        score = 0 if self.env.err_tk == 3 else sum(len(self.env.table_cards[k]) for k in COLORS)
        self.value += score

    def expand(self):
        for i in range(len(self.valid_moves)):
            if self.expanded[i] == False and self.valid_moves[i] == True:
                n = Node((self.player_idx + 1) % self.env.num_players, self.__hands_knowledge, 
                        self.__board, self.__pile, self.__player_hands, self.__info_tk, self.__err_tk, 
                        self.env.num_players)
                ok = False
                if i == 0: ok = n.play_probably_safe_card(self.player_idx, 0.7) # first param: who performs action
                elif i == 1: ok = n.discard_probably_useless_card(self.player_idx, 0.0)
                elif i == 2: ok = n.tell_anyone_about_useful_card(self.player_idx)
                elif i == 3: ok = n.tell_dispensable(self.player_idx)
                elif i == 4: ok = n.tell_most_info(self.player_idx)
                self.expanded[i] = True
                if ok: 
                    n.action = i
                    self.children.append(n)
                    return
                else:
                    self.valid_moves[i] = False
                    continue
            else: self.expanded[i] = True

    def select(self, C=2):
        max_UCB = 0
        selected_child = None
        for child in self.children:
            UCB = (child.value / child.num_visits) + C*np.sqrt(2*np.log(Node.total_visits) / child.num_visits)
            if UCB > max_UCB or selected_child is None:
                max_UCB = UCB
                selected_child = child
        return selected_child

    def backprop(self, node, value, num_visits):
        if node.parent is not None:
            node.parent.value += value
            node.parent.num_visits += num_visits
            node.backprop(node.parent, value, num_visits)

def MCTS(current_state, timeout=1.0, C=2):
    Node.total_visits = 0
    root = Node(*current_state)
    saved_hand = []

    timeout = time.time() + timeout
    while time.time() <= timeout:
        root.redetermine()
        node = root
        
        while node.fully_expanded():
            new_node = node.select(C)

            if node.player_idx != root.player_idx:
                node.hand = saved_hand
                # remove from hand incompatible cards with observation + sample new cards
                node.remove_and_determine_incompatible_cards() 
            
            node = new_node

            if node.player_idx != root.player_idx:
                saved_hand = node.hand.copy()
                node.hand = node.redetermine()
        
        node.expand()
        score = node.simulate()
        node.backprop(node, score, node.num_visits)
    
    return root.select(C).action


