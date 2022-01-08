import random

COLORS = ['red','yellow','green','white','blue']
VALUES = range(1,5+1)

def deepcopy(d: 'dict[str, list]'): return {key: d[key].copy() for key in d.keys()}

class Hanabi:
    def __init__(self, num_players=2, verbose=False):
        self.num_players = num_players
        self.hand_size = 5 if num_players < 4 else 4
        self.verbose = verbose

    def compute_actions(self, player_idx):
        actions = []
        count = 0
        if self.err_tk < 3:
            for _ in self.hands_knowledge[player_idx]: # Plays
                actions.append(count)
                count += 1
        count = 5
        if self.info_tk > 0:
            for _ in self.hands_knowledge[player_idx]: # Discards
                actions.append(count)
                count += 1
        
        if self.info_tk < 8:
            for pl in range(self.num_players):
                player = (player_idx + pl) % self.num_players
                if player != player_idx:
                    colors = {k: 0 for k in COLORS}
                    values = {v: 0 for v in VALUES}
                    for card in self.player_hands[player]:
                        colors[card[0]] += 1
                        values[card[1]] += 1
                    for j, k in enumerate(colors.keys()):
                        if colors[k] > 0: actions.append(10 + (pl-1) * 5 + j)
                    for j, k in enumerate(values.keys()):
                        if values[k] > 0: actions.append(10+5*(self.num_players-1) + (pl-1) * 5 + j)
        return actions

    def reset(self):
        self.info_tk = 0 # max 8
        self.err_tk = 0 # max 3
        self.last_action = None
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
        self.hands_knowledge = [[('',0) for __ in range(self.hand_size)] for _ in range(self.num_players)]
        self.played_last_turn = [False for _ in range(self.num_players)]
    
    def set_state(self, hands_knowledge, board, pile, info_tk, err_tk, player_hands, deck, played_last_turn):
        self.info_tk = info_tk
        self.err_tk = err_tk
        self.last_turn = len(deck) == 0
        self.deck = deck.copy()
        self.table_cards = deepcopy(board)
        self.discard_pile = pile.copy()
        self.player_hands = [player_hands[i].copy() for i in range(self.num_players)]
        self.hands_knowledge = [hands_knowledge[i].copy() for i in range(self.num_players)]
        self.played_last_turn = played_last_turn.copy()
    
    def is_final_state(self):
        return self.err_tk == 3 or (len(self.deck) == 0 and all(self.played_last_turn)) or sum(len(self.table_cards[k]) for k in COLORS) == 25
    
    def final_score(self):
        if self.err_tk == 3: return 0
        return sum(len(self.table_cards[k]) for k in COLORS)
    
    def __action_play(self, player_idx, num):
        self.hands_knowledge[player_idx].pop(num)
        if len(self.deck) > 0:
            self.hands_knowledge[player_idx].append(['',0])

        c, v = self.player_hands[player_idx].pop(num)
        if len(self.deck) > 0: 
            self.player_hands[player_idx].append(self.deck.pop())
        else: 
            self.last_turn = True
        if self.last_turn: self.played_last_turn[player_idx] = True

        self.last_action = (player_idx, num, (c,v), False, False)

        if v == len(self.table_cards[c]) + 1:
            self.table_cards[c].append((c,v))
            if len(self.table_cards[c]) == 5 and self.info_tk > 0: 
                self.info_tk -= 1
        else:
            self.discard_pile.append((c,v))
            self.err_tk += 1
    
    def __action_discard(self, player_idx, num):
        self.hands_knowledge[player_idx].pop(num)
        if len(self.deck) > 0:
            self.hands_knowledge[player_idx].append(['',0])

        c, v = self.player_hands[player_idx].pop(num)
        if len(self.deck) > 0: 
            self.player_hands[player_idx].append(self.deck.pop())
        else: 
            self.last_turn = True
        if self.last_turn: self.played_last_turn[player_idx] = True

        self.discard_pile.append((c,v))
        self.info_tk -= 1

    def __action_hint(self, player_idx, type, to, value):
        self.info_tk += 1

        for i, card in enumerate(self.player_hands[to]):
            if type == 'color':
                if card[0] == value:
                    self.hands_knowledge[to][i] = (value, card[1])
            else:
                if card[1] == value:
                    self.hands_knowledge[to][i] = (card[0], value)

        if self.last_turn: self.played_last_turn[player_idx] = True
        
    def step(self, player_idx, action):
        if action in range(0,5): # play 0-4
            err = self.err_tk
            self.__action_play(player_idx, action)
            if self.verbose: print(f'P{player_idx+1} Play {action} {"ERROR" if self.err_tk != err else "OK"}')
        elif action in range(5,10): # discard 0-4
            self.__action_discard(player_idx, action - 5)
            if self.verbose: print(f'P{player_idx+1} Discard {action-5}')
        elif action in range(10,10+5*(self.num_players-1)): # hint color to_next_player [COLORS]
            to = (player_idx + ((action - 10) // 5) + 1) % self.num_players
            color = COLORS[(action-10)%5]
            self.__action_hint(player_idx, 'color', to, color)
            if self.verbose: print(f'P{player_idx+1} Hint P{to+1} Color {color}')
        elif action in range(10+5*(self.num_players-1),10+5*(self.num_players-1)*2): # hint value to_next_player 1-5
            start_val = 10+5*(self.num_players-1)
            to = (player_idx + ((action - start_val) // 5) + 1) % self.num_players
            value = ((action-start_val)%5)+1
            self.__action_hint(player_idx, 'value', to, value)
            if self.verbose: print(f'P{player_idx+1} Hint P{to+1} Value {value}')