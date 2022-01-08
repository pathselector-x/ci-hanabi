import random

COLORS = ['red','yellow','green','white','blue']
VALUES = range(1,5+1)

def deepcopy(d: 'dict[str, list]'): return {key: d[key].copy() for key in d.keys()}

class Hanabi:
    def __init__(self, num_players=2, view_colors=['red','white','green','blue','yellow'], verbose=False):
        #self.num_actions = 21 # P0-4, D0-4, HCR-W, HV1-5, Invalid/deal
        self.num_players = num_players
        self.hand_size = 5 if num_players < 4 else 4
        #self.state_size = 838
        self.view_colors = view_colors
        self.verbose = verbose
        #self.reset()

    def __interrupted_pile(self, color):
        val_to_test = len(self.table_cards[color]) + 1
        max_count = 2 if val_to_test in [2,3,4] else (3 if val_to_test == 1 else 1)
        count = 0
        for c, v in self.discard_pile:
            if c == color and v == val_to_test:
                count += 1
        if count == max_count: # all have been discarded, we can't cont. the pile
            return True
        return False
    
    def __one_copy_left(self, color, value):
        max_count = 2 if value in [2,3,4] else (3 if value == 1 else 1)
        count = 0
        for c, v in self.discard_pile:
            if c == color and v == value:
                count += 1
        if max_count - count == 1:
            return True
        return False

    def encode(self, player_idx):
        bits_per_card = 25
        hands_section_length = 252
        boards_section_length = 76
        discard_section_length = 50
        last_action_section_length = 55
        card_knowledge_section_length = 350
        shape = hands_section_length + boards_section_length + \
            discard_section_length + last_action_section_length + \
            card_knowledge_section_length
        encoding = [0 for _ in range(shape + 55)] #TODO why 838?
        offset = 0
        
        # Encode hands
        num_cards = 0
        for c, v in self.player_hands[(player_idx + 1) % 2]:
            card_idx = COLORS.index(c) * 5 + (v-1)
            encoding[offset + card_idx] = 1
            num_cards += 1
            offset += bits_per_card
        if num_cards < 5:
            offset += (5 - num_cards) * bits_per_card
        for p in range(self.num_players):
            if len(self.player_hands[p]) < 5:
                encoding[offset + p] = 1
        offset += self.num_players

        # Encode board
        for i in range(len(self.deck)):
            encoding[offset + i] = 1
        offset += (50 - 5 * self.num_players)
        
        for c in COLORS:
            if len(self.table_cards[c]) > 0:
                encoding[offset + len(self.table_cards[c]) - 1] = 1
            offset += 5
        
        for i in range(8):
            encoding[offset + i] = 1
        offset += 8

        for i in range(3):
            encoding[offset + i] = 1
        offset += 3

        # Encode discards
        discard_counts = [0 for _ in range(25)]
        for c, v in self.discard_pile:
            card_idx = COLORS.index(c) * 5 + (v-1)
            discard_counts[card_idx] += 1
        
        for col in COLORS:
            for val in range(5):
                card_idx = COLORS.index(col) * 5 + (val-1)
                num_discarded = discard_counts[card_idx]
                for i in range(num_discarded):
                    encoding[offset + i] = 1
                offset += 3 if val == 1 else (1 if val == 5 else 2)
        
        # Encode last action
        if self.last_action is None:
            offset += last_action_section_length
        else:
            performer = self.last_action[0]
            move = self.last_action[1]

            if move in range(5): # Play
                encoding[offset] = 1
                card = self.last_action[2]
                scored, info_tk = self.last_action[3], self.last_action[4]
            elif move in range(5,10): # Discard
                encoding[offset + 1] = 1
                card = self.last_action[2]
            elif move in range(10,15): # Reveal Color
                encoding[offset + 2] = 1
                reveal_bitmask = self.last_action[2]
            elif move in range(15,20): # Reveal Value
                encoding[offset + 3] = 1
                reveal_bitmask = self.last_action[2]
            
            offset += 4
            
            if move in range(10,20): # target p if hint
                encoding[offset + (performer + 1) % 2] = 1
            offset += 2

            if move in range(10,15):
                encoding[offset + move - 10] = 1
            offset += 5
            if move in range(15,20):
                encoding[offset + move - 15] = 1
            offset += 5

            if move in range(10,20):
                mask = 4
                for i in range(5):
                    if reveal_bitmask[mask] == 1:
                        encoding[offset + i] = 1
            offset += 5
                
            if move in range(10):
                #card_idx = COLORS.index(card[0]) * 5 + (card[1]-1)
                hand_idx = move - (0 if move in range(5) else 5)
                encoding[offset + hand_idx] = 1
            offset += 5

            if move in range(10):
                card_idx = COLORS.index(card[0]) * 5 + (card[1]-1)
                encoding[offset + card_idx] = 1
            offset += bits_per_card

            if move in range(5):
                if scored: encoding[offset] = 1
                if info_tk: encoding[offset + 1] = 1
            offset += 2
        
        # Encode V0 Belief
        start_offset = offset
        # Compute card count
        card_count = [0 for _ in range(25)]
        total_count = 0
        for c in COLORS:
            for v in VALUES:
                count = 3 if v == 1 else (1 if v == 5 else 2)
                card_count[COLORS.index(c) * 5 + (v-1)] = count
                total_count += count
        for c, v in self.discard_pile:
            card_count[COLORS.index(c) * 5 + (v-1)] -= 1
            total_count -= 1
        for k in COLORS:
            for c, v in self.table_cards[k]:
                card_count[COLORS.index(c) * 5 + (v-1)] -= 1
                total_count -= 1
        
        # card knowledge
        for p in range(self.num_players):
            num_cards = 0
            for c, v in self.hands_knowledge[p]:
                if c != '' and v != 0:
                    card_idx = COLORS.index(c) * 5 + (v-1)
                    encoding[offset + card_idx] = 1
                offset += bits_per_card

                if c != '':
                    encoding[offset + COLORS.index(c)] = 1
                offset += 5

                if v != 0:
                    encoding[offset + (v-1)] = 1
                offset += 5

                num_cards += 1
            if num_cards < 5:
                offset += (5 - num_cards) * (bits_per_card + 10)
        length = offset - start_offset
        player_offset = length // self.num_players
        per_card_offset = length // 5 // self.num_players

        for player_id in range(self.num_players):
            num_cards = len(self.player_hands[player_id])
            for card_idx in range(num_cards):
                total = 0
                for i in range(25):
                    off = start_offset + player_offset * player_id + card_idx * per_card_offset + i
                    encoding[off] = 1
                    encoding[off] *= card_count[i]
                    total += encoding[off]
                for i in range(25):
                    off = start_offset + player_offset * player_id + card_idx * per_card_offset + i
                    encoding[off] /= total

        return encoding

    def compute_own_hand(self, player_idx):
        encoding = [0 for _ in range(self.hand_size * 3)]
        offset = 0
        for c, v in self.hands_knowledge[player_idx]:
            if c != '':
                firework = self.table_cards[c]
                if v == len(firework) + 1: 
                    encoding[offset] = 1
                elif v <= len(firework): 
                    encoding[offset + 1] = 1
                else: 
                    encoding[offset + 2] = 1
            else:
                encoding[offset + 2] = 1
            offset += 3
        return encoding

    def compute_legal_action(self, player_idx):
        actions = []
        if self.err_tk == 3:
            for _ in range(10+5*(self.num_players-1)*2): actions.append(0)
            return actions
        else:
            for _ in range(5): actions.append(1)
        if self.info_tk == 0:
            for _ in range(5): actions.append(0)
        else:
            for _ in range(5): actions.append(1)
        for player in range(self.num_players):
            if player != player_idx:
                if self.info_tk == 8:
                    for _ in range(10): actions.append(0)
                else:
                    #for _ in range(10): actions.append(0)
                    #start_val = 10+5*(self.num_players-1)
                    admissible_colors = [1 for k in COLORS]
                    admissible_values = [1 for v in VALUES]
                    for i, col in enumerate(COLORS):
                        if all(c != col for c, _ in self.player_hands[player]):
                            admissible_colors[i] = 0
                    for i, val in enumerate(VALUES):
                        if all(v != val for _, v in self.player_hands[player]):
                            admissible_values[i] = 0
                    for k in admissible_colors:
                        actions.append(k)
                    for v in admissible_values:
                        actions.append(v)
                actions.append(0)
        return actions
            
    def compute_state(self, player_idx, permute_colors=False): # state is just a belief
        self.state = [0 for _ in range(50)]
        if permute_colors:
            for c, v in self.deck:
                self.state[self.view_colors.index(c) * 5 + v - 1] = 1
        else:
            for c, v in self.deck:
                self.state[COLORS.index(c) * 5 + v - 1] = 1
        if len(self.state) < 50: print('ERROR in deck')
        for c, v in self.hands_knowledge[player_idx]:
            if c != '' and v != 0:
                if permute_colors:
                    self.state.append(self.view_colors.index(c))
                else:
                    self.state.append(COLORS.index(c))
                self.state.append(v)
            elif c != '':
                if permute_colors:
                    self.state.append(self.view_colors.index(c))
                else:
                    self.state.append(COLORS.index(c))
                self.state.append(v)
            elif v != 0:
                self.state.append(0)
                self.state.append(v)
            else:
                self.state.append(0)
                self.state.append(0)
        if len(self.state) < 60: print('ERROR in my kn')
        for p_idx in list(set(range(self.num_players))-set([player_idx])):
            for c, v in self.hands_knowledge[p_idx]:
                if c != '' and v != 0:
                    if permute_colors:
                        self.state.append(self.view_colors.index(c))
                    else:
                        self.state.append(COLORS.index(c))
                    self.state.append(v)
                elif c != '':
                    if permute_colors:
                        self.state.append(self.view_colors.index(c))
                    else:
                        self.state.append(COLORS.index(c))
                    self.state.append(v)
                elif v != 0:
                    self.state.append(0)
                    self.state.append(v)
                else:
                    self.state.append(0)
                    self.state.append(0)
        if len(self.state) < 70: print('ERROR in op kn')
        for p_idx in list(set(range(self.num_players))-set([player_idx])):
            for c, v in self.player_hands[p_idx]:
                if permute_colors:
                    self.state.append(self.view_colors.index(c))
                else:
                    self.state.append(COLORS.index(c))
                self.state.append(v)
            if len(self.player_hands[p_idx]) < 5: #TODO: solve bug
                self.state.append(0)
                self.state.append(0)
        if len(self.state) < 80: print('ERROR in op hand')
        if permute_colors:
            for k in self.view_colors:
                self.state.append(len(self.table_cards[k])) 
        else:
            for k in COLORS:
                self.state.append(len(self.table_cards[k]))
        if len(self.state) < 85: print('ERROR in table')
        self.state.append(self.info_tk)
        return self.state

    def is_valid(self, action):
        if action in range(0,5): # play 0-4
            return True
        elif action in range(5,10): # discard 0-4
            if self.info_tk == 0: return False
            return True
        elif action in range(10,20): # hint
            if self.info_tk == 8: return False
            return True

    def compute_actions(self, player_idx):
        #assert len(self.hands_knowledge[player_idx]) == len(self.player_hands[player_idx])
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

    def reset(self, player_idx, permute_colors=False):
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
        self.hands_knowledge = [[['',0] for __ in range(self.hand_size)] for _ in range(self.num_players)]
        self.played_last_turn = [False for _ in range(self.num_players)]
        return #self.compute_state(player_idx, permute_colors) #self.encode(player_idx) #
    
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
        done = False
        reward = 0

        if num >= len(self.player_hands[player_idx]):
            print('Whoops! ', len(self.player_hands[player_idx]), num)
        self.hands_knowledge[player_idx].pop(num)
        if len(self.deck) > 0:
            self.hands_knowledge[player_idx].append(['',0])

        c, v = self.player_hands[player_idx].pop(num)
        if len(self.deck) > 0: self.player_hands[player_idx].append(self.deck.pop())
        else: self.last_turn = True
        if self.last_turn: self.played_last_turn[player_idx] = True

        self.last_action = (player_idx, num, (c,v), False, False)

        if v == len(self.table_cards[c]) + 1:
            self.table_cards[c].append((c,v))
            reward = 5 + v
            if len(self.table_cards[c]) == 5 and self.info_tk > 0: 
                self.info_tk -= 1
            if all(len(self.table_cards[k]) == 5 for k in COLORS):
                reward = 100
                done = True
            self.last_action = (player_idx, num, (c,v), True, True)
            return reward, done # reward
        else:
            self.discard_pile.append((c,v))
            self.err_tk += 1
            reward = -33
            if self.err_tk == 3:
                reward = -100
                done = True
            return reward, done
    
    def __action_discard(self, player_idx, num):
        done = False
        reward = 0

        self.hands_knowledge[player_idx].pop(num)
        if len(self.deck) > 0:
            self.hands_knowledge[player_idx].append(['',0])

        c, v = self.player_hands[player_idx].pop(num)
        if len(self.deck) > 0: self.player_hands[player_idx].append(self.deck.pop())
        else: self.last_turn = True
        if self.last_turn: self.played_last_turn[player_idx] = True

        self.last_action = (player_idx, num+5, (c,v))

        self.discard_pile.append((c,v))
        self.info_tk -= 1

        if v <= len(self.table_cards[c]) or self.__interrupted_pile(c): # useless
            reward = 5
        else:
            max_count = 2 if v in [2,3,4] else (3 if v == 1 else 1)
            count = 0
            for card in self.discard_pile:
                if card[0] == c and card[1] == v:
                    count += 1
            if count == max_count: reward = v - 6 - 5 # i've interrupted a pile
            else: reward = 1

        return reward, done

    def __action_hint(self, player_idx, type, to, value):
        reward = 0
        self.info_tk += 1

        prev_kn = [['',0] for _ in range(self.hand_size)]
        for i, card in enumerate(self.hands_knowledge[to]):
            prev_kn[i][0] = card[0]
            prev_kn[i][1] = card[1]

        reveal_bitmask = [0 for _ in range(5)]
        for i, card in enumerate(self.player_hands[to]):
            if card[0 if type == 'color' else 1] == value:
                self.hands_knowledge[to][i][0 if type == 'color' else 1] = value
                reveal_bitmask[i] = 1
        if self.last_turn: self.played_last_turn[player_idx] = True

        if type == 'color':
            self.last_action = (player_idx, COLORS.index(value)+10, reveal_bitmask)
        else:
            self.last_action = (player_idx, value+14, reveal_bitmask)

        already_hinted = True
        for prev, new in zip(prev_kn, self.hands_knowledge[to]):
            if prev[0] != new[0] or prev[1] != new[1]:
                already_hinted = False
                break
        if already_hinted: reward = -33
        else:
            reward = 1
            idx = 0
            for prev, new in zip(prev_kn, self.hands_knowledge[to]):
                if prev[1] != new[1] and \
                    self.hands_knowledge[to][idx][0] != '' and \
                    self.player_hands[to][idx][1] == len(self.table_cards[self.hands_knowledge[to][idx][0]]) + 1: # directly playable
                    reward = 5
                    break
                elif prev[1] != new[1] and \
                    all(self.player_hands[to][idx][1] == len(self.table_cards[k]) + 1 for k in COLORS): # directly playable
                    reward = 5
                    break
                idx += 1
            idx = 0
            for prev, new in zip(prev_kn, self.hands_knowledge[to]):
                if prev[1] != new[1] and \
                    self.hands_knowledge[to][idx][0] != '' and \
                    self.player_hands[to][idx][1] <= len(self.table_cards[self.hands_knowledge[to][idx][0]]): # directly discardable
                    reward = 5
                    break
                elif prev[1] != new[1] and \
                    all(self.player_hands[to][idx][1] <= len(self.table_cards[k]) for k in COLORS): # directly discardable
                    reward = 5
                    break
                idx += 1

        return reward, False
        
    def step(self, player_idx, action, permute_colors=False):
        
        if action in range(0,5): # play 0-4
            err = self.err_tk
            reward, done = self.__action_play(player_idx, action)
            if self.verbose: print(f'P{player_idx+1} Play {action} {"ERROR" if self.err_tk != err else "OK"}')
        elif action in range(5,10): # discard 0-4
            reward, done = self.__action_discard(player_idx, action - 5)
            if self.verbose: print(f'P{player_idx+1} Discard {action-5}')
        elif action in range(10,10+5*(self.num_players-1)): # hint color to_next_player [COLORS]
            to = (player_idx + ((action - 10) // 5) + 1) % self.num_players
            color = COLORS[(action-10)%5]
            reward, done = self.__action_hint(player_idx, 'color', to, color)
            if self.verbose: print(f'P{player_idx+1} Hint P{to+1} Color {color}')
        elif action in range(10+5*(self.num_players-1),10+5*(self.num_players-1)*2): # hint value to_next_player 1-5
            start_val = 10+5*(self.num_players-1)
            to = (player_idx + ((action - start_val) // 5) + 1) % self.num_players
            value = ((action-start_val)%5)+1
            reward, done = self.__action_hint(player_idx, 'value', to, value)
            if self.verbose: print(f'P{player_idx+1} Hint P{to+1} Value {value}')
        #next_state = self.compute_state(player_idx, permute_colors)#self.encode(player_idx) #

        #if all(self.played_last_turn): done = True
        #if done: 
        #    done = 1
        #    reward = 0.0
        #    if self.err_tk < 3:
        #        for k in COLORS:
        #            reward += len(self.table_cards[k])
        #else: 
        #    done = 0
        #    reward = 0.0

        return #next_state, reward, done, None
