from itertools import product
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
        pass

    def draw(self): #TODO: used when we need to reconcile a sampled hand with the move performed
        pass

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

NUM_MOVES = 5

def play_probably_safe_card(state: State, threshold=0.7): pass #TODO
def discard_probably_useless_card(state: State, threshold=0.0): pass #TODO
def tell_anyone_about_useful_card(state: State): pass #TODO
def tell_dispensable(state: State): pass #TODO
def tell_most_info(state: State): pass #TODO

MOVES = [play_probably_safe_card, discard_probably_useless_card, tell_anyone_about_useful_card, tell_dispensable, tell_most_info]

class Node:
    total_visits = 0

    def __init__(self, state: State, action=None, parent=None):
        self.state = state.copy()
        self.state.sample_hand()
        self.action = action
        self.parent = parent
        self.num_visits = 0
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
        root = State(self.player_idx, self.env.player_hands, self.env.hands_knowledge, self.env.played_last_turn, self.env.table_cards, self.env.discard_pile, self.env.info_tk, self.env.err_tk)
        timeout = time.time() + timeout
        while time.time() <= timeout:
            terminal = False
            root.sample_hand()
            node = root

            while node.fully_expanded():
                node = node.select(C)

                if node is None: 
                    terminal = True
                    break

                if node.player_idx != root.player_idx:
                    node.sample_hand()

            if terminal: continue
            
            expanded_node = node.expand()
            score = expanded_node.simulate()
            expanded_node.backprop(expanded_node, score, expanded_node.num_visits)
        return root.select(C).action


