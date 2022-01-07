from sys import argv, stdout
from threading import Thread, Lock, Condition
from itertools import product
import random
import numpy as np

import GameData
import socket
from constants import *

from game import Card

COLORS = ['red','yellow','green','blue','white']
VALUES = range(1,5+1)

class Hanabi: #! Simulation environment
    def __init__(self, player_name: str, num_players: int, player_hands: 'dict[str, list[Card]]', 
            hands_knowledge: 'dict[str, list[list]]', table_cards: 'dict[str, list[Card]]', discard_pile: 'list[Card]', deck: 'list[Card]', 
            info_tk: int, err_tk: int, played_last_turn: 'list[bool]', play_order: 'list[str]'):
        self.player_name = player_name # name of the moving player
        self.num_players = num_players
        self.player_hands = {}
        for k in player_hands.keys():
            self.player_hands[k] = [Card(card.id, card.value, card.color) for card in player_hands[k]]
        self.hands_knowledge = {}
        self.table_cards = {}
        for k in COLORS:
            self.table_cards[k] = [Card(card.id, card.value, card.color) for card in table_cards[k]]
        for k in hands_knowledge.keys():
            self.hands_knowledge[k] = [kn.copy() for kn in hands_knowledge[k]]
        self.discard_pile = [Card(card.id, card.value, card.color) for card in discard_pile]
        self.deck = [Card(card.id, card.value, card.color) for card in deck]
        self.info_tk = info_tk
        self.err_tk = err_tk
        self.played_last_turn = {}
        for k in played_last_turn.keys():
            self.played_last_turn[k] = played_last_turn[k]
        self.play_order = play_order.copy() 
        self.player_idx = 0 # play_order starts always with the moving player i.e. playerName at idx 0

    def is_final_state(self):
        return (len(self.deck) == 0 and all(self.played_last_turn[k] for k in self.played_last_turn.keys())) or \
            self.err_tk == 3 or sum(len(self.table_cards[k]) for k in COLORS) == 25
    
    def final_score(self):
        if self.err_tk == 3: return 0
        return sum(len(self.table_cards[k]) for k in COLORS)

    def valid_actions(self, player_name):
        #if self.is_final_state(): return []
        actions = []
        for i, _ in enumerate(self.player_hands[player_name]):
            actions.append({'action': 'play', 'num': i})
            if self.info_tk > 0:
                actions.append({'action': 'discard', 'num': i})
        if self.info_tk < 8:
            for player in self.play_order:
                if player == player_name: continue
                
                hintable_colors = set([])
                hintable_values = set([])
                for card in self.player_hands[player]:
                    hintable_colors.add(card.color)
                    hintable_values.add(card.value)
                
                for color in hintable_colors:
                    actions.append({'action': 'hint', 'type': 'color', 'to': player,'value': color})
                for value in hintable_values:
                    actions.append({'action': 'hint', 'type': 'value', 'to': player, 'value': value})
        return actions

    def __play(self, player, num):
        #assert not self.is_final_state()
        assert len(self.player_hands[player]) == len(self.hands_knowledge[player])
        card = self.player_hands[player].pop(num)
        self.hands_knowledge[player].pop(num)

        if card.value == len(self.table_cards[card.color]) + 1:
            self.table_cards[card.color].append(card)
            if len(self.table_cards[card.color]) == 5:
                self.info_tk -= 1
        else:
            self.discard_pile.append(card)
            self.err_tk += 1

        # Draw a card
        if len(self.deck) > 0:
            self.player_hands[player].append(self.deck.pop())
            self.hands_knowledge[player].append(['',0])
        else:
            self.played_last_turn[player] = True
        
        self.player_idx = (self.player_idx + 1) % self.num_players

    def __discard(self, player, num):
        #assert not self.is_final_state() and 
        assert self.info_tk > 0
        assert len(self.player_hands[player]) == len(self.hands_knowledge[player])
        card = self.player_hands[player].pop(num)
        self.hands_knowledge[player].pop(num)

        self.discard_pile.append(card)
        self.info_tk -= 1

        # Draw a card
        if len(self.deck) > 0:
            self.player_hands[player].append(self.deck.pop())
            self.hands_knowledge[player].append(['',0])
        else:
            self.played_last_turn[player] = True
        
        self.player_idx = (self.player_idx + 1) % self.num_players

    def __hint(self, player, type, to, value): 
        #assert not self.is_final_state() 
        assert self.info_tk < 8
        assert len(self.player_hands[to]) == len(self.hands_knowledge[to])
        
        for i in range(len(self.player_hands[to])):
            if type == 'color':
                if self.player_hands[to][i].color == value:
                    self.hands_knowledge[to][i][0] = value
            else:
                if self.player_hands[to][i].value == value:
                    self.hands_knowledge[to][i][1] = value

        self.info_tk += 1

        if len(self.deck) == 0:
            self.played_last_turn[player] = True
        
        self.player_idx = (self.player_idx + 1) % self.num_players

    def step(self, player_name: str, action: 'dict[str, str]'):
        # player_name: who performs the action
        # action: dict containing the action e.g. 
        # {'action': 'play', 'num': 0} {'action': 'discard', 'num': 4} 
        # {'action': 'hint', 'type': 'color', 'to': 'other p. name', 'value': 'red'}
        # {'action': 'hint', 'type': 'value', 'to': 'other p. name', 'value': 4}
        if action['action'] == 'play': self.__play(player_name, action['num'])
        elif action['action'] == 'discard': self.__discard(player_name, action['num'])
        elif action['action'] == 'hint': self.__hint(player_name, action['type'], action['to'], action['value'])
        return self.is_final_state()

class Agent: #! Simple agent that plays according to blueprint strategy
    def __init__(self, player_name, env: Hanabi):
        self.player_name = player_name
        self.env = env
    
    def __interrupted_pile(self, color):
        for v in range(len(self.env.table_cards[color]) + 1, 6):
            count = 3 if v == 1 else (1 if v == 5 else 2)
            for card in self.env.discard_pile:
                if card.color == color and card.value == v:
                    count -= 1
            if count == 0: return True
        return False

    def __play_probably_safe_card(self, threshold=0.7): 
        knowledge = self.env.hands_knowledge[self.player_name]
        p = []
        for c, v in knowledge:
            if c != '' and v != 0:
                playable_val = len(self.env.table_cards[c]) + 1
                if v == playable_val: p.append(1.0)
                else: p.append(0.0)
                
            elif c != '':
                playable_val = len(self.env.table_cards[c]) + 1
                how_many = 3 if playable_val == 1 else (1 if playable_val == 5 else 2)
                total = 10

                for card in self.env.discard_pile:
                    if card.color == c and card.value == playable_val:
                        how_many -= 1
                    if card.color == c: total -= 1

                for player in self.env.player_hands.keys():
                    if player != self.player_name:
                        for card in self.env.player_hands[player]:
                            if card.color == c and card.value == playable_val:
                                how_many -= 1
                            if card.color == c: total -= 1

                p.append(how_many / total)
            
            elif v != 0:
                piles_playable = [k for k in COLORS if v == len(self.env.table_cards[k]) + 1]
                how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(piles_playable)
                total = (3 if v == 1 else (1 if v == 5 else 2)) * 5

                for card in self.env.discard_pile:
                    if card.color in piles_playable and card.value == v:
                        how_many -= 1
                    if card.value == v: total -= 1

                for player in self.env.player_hands.keys():
                    if player != self.player_name:
                        for card in self.env.player_hands[player]:
                            if card.color in piles_playable and card.value == v:
                                how_many -= 1
                            if card.value == v: total -= 1
                
                p.append(how_many / total)
            
            else:
                min_p = 1.0
                total = 50 - len(self.env.discard_pile) - \
                    sum(len(self.env.table_cards[k]) for k in COLORS) - \
                    sum(len(self.env.player_hands[p]) for p in self.env.player_hands.keys() if p != self.player_name)
                vals = {}
                for k in COLORS:
                    pv = len(self.env.table_cards[k]) + 1
                    if pv > 5: continue
                    if pv not in vals.keys(): vals[pv] = [k]
                    else: vals[pv].append(k)

                for v in vals.keys():
                    colors = vals[v]
                    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                    for card in self.env.discard_pile:
                        if card.color in colors and card.value == v:
                            how_many -= 1
                    for player in self.env.player_hands.keys():
                        if player != self.player_name:
                            for card in self.env.player_hands[player]:
                                if card.color in colors and card.value == v:
                                    how_many -= 1
                    min_p = min(min_p, how_many / total)
                p.append(min_p)
        
        idx_to_play = np.argmax(p)
        if p[idx_to_play] >= threshold:
            action = {'action': 'play', 'num': idx_to_play}
            self.env.step(self.player_name, action)
            return True, action
        return False, None

    def __play_safe_card(self): 
        ok, action = self.__play_probably_safe_card(1.0)
        return ok, action

    def __discard_probably_useless_card(self, threshold=0.0):
        kn = self.env.hands_knowledge[self.player_name]
        # calc prob of being useless
        p = []
        for c, v in kn:
            if c != '' and v != 0:
                if v <= len(self.env.table_cards[c]) or \
                    len(self.env.table_cards[c]) == 5 or\
                    self.__interrupted_pile(c):
                    p.append(1.0)
                else:
                    p.append(0.0)
            elif c != '':
                if len(self.env.table_cards[c]) == 5 or\
                    self.__interrupted_pile(c):
                    p.append(1.0)
                else:
                    count = [3,2,2,2,1]
                    total = 10
                    v_lte = len(self.env.table_cards[c])
                    how_many = sum(count[:v_lte])
                    for card in self.env.discard_pile:
                        if card.color == c and card.value <= v_lte:
                            how_many -= 1
                        if card.color == c: total -= 1
                    for player in self.env.player_hands.keys():
                        if player != self.player_name:
                            for card in self.env.player_hands[player]:
                                if card.color == c and card.value <= v_lte:
                                    how_many -= 1
                                if card.color == c: total -= 1
                    p.append(how_many / total)
                    continue
            elif v != 0:
                if all(v <= len(self.env.table_cards[k]) for k in COLORS):
                    p.append(1.0)
                else:
                    total = (3 if v == 1 else (1 if v == 5 else 2)) * 5
                    colors = []
                    for k in COLORS:
                        if v == len(self.env.table_cards[k]) + 1:
                            colors.append(k)
                        
                    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                    for card in self.env.discard_pile:
                        if card.color in colors and card.value == v:
                            how_many -= 1
                        if card.value == v: total -= 1
                    for player in self.env.player_hands.keys():
                        if player != self.player_name:
                            for card in self.env.player_hands[player]:
                                if card.color in colors and card.value == v:
                                    how_many -= 1
                                if card.value == v: total -= 1
                    p.append(how_many / total)
            else:
                p.append(0.0)
        
        idx_to_discard = np.argmax(p)
        if all(pv == p[0] for pv in p): idx_to_discard = 0
        if p[idx_to_discard] >= threshold:
            action = {'action': 'discard', 'num': idx_to_discard}
            self.env.step(self.player_name, action)
            return True, action
        return False, None

    def __tell_anyone_about_useful_card(self): 
        for player in self.env.play_order:
            if player != self.player_name:
                hand = self.env.player_hands[player]
                kn = self.env.hands_knowledge[player]
                for (kc, kv), card in zip(kn, hand):
                    c, v = card.color, card.value
                    if len(self.env.table_cards[c]) + 1 == v:
                        if kc != '' and kv != 0: continue
                        if kv == 0:
                            action = {'action': 'hint', 'type': 'value', 'to': player, 'value': v}
                            self.env.step(self.player_name, action)
                            return True, action
                        if kc == '':
                            action = {'action': 'hint', 'type': 'color', 'to': player, 'value': c}
                            self.env.step(self.player_name, action)
                            return True, action
        return False, None

    def __tell_disposable(self):
        for player in self.env.play_order:

            if player != self.player_name:
                hand = self.env.player_hands[player]
                kn = self.env.hands_knowledge[player]

                for (kc, kv), card in zip(kn, hand):
                    c, v = card.color, card.value
                    if v <= len(self.env.table_cards[c]) and kv == 0:
                        action = {'action': 'hint', 'type': 'value', 'to': player, 'value': v}
                        self.env.step(self.player_name, action)
                        return True, action
                    elif (len(self.env.table_cards[c]) == 5 or self.__interrupted_pile(c)) and kc == '':
                        action = {'action': 'hint', 'type': 'color', 'to': player, 'value': c}
                        self.env.step(self.player_name, action)
                        return True, action
        return False, None

    def __tell_randomly(self): 
        legal_actions = self.env.valid_actions(self.player_name)
        legal_actions = [a for a in legal_actions if a['action'] == 'hint']
        action = random.choice(legal_actions)
        self.env.step(self.player_name, action)
        return True, action
    
    def act(self):
        if self.env.err_tk < 2 and len(self.env.deck) == 0:
            ok, action = self.__play_probably_safe_card(0.0)
            if ok: return action
        
        ok, action = self.__play_safe_card()
        if ok: return action

        if self.env.err_tk < 3:
            ok, action = self.__play_probably_safe_card(0.7)
            if ok: return action

        if self.env.info_tk < 8:
            ok, action = self.__tell_anyone_about_useful_card()
            if ok: return action

        if self.env.info_tk > 4 and self.env.info_tk < 8:
            ok, action = self.__tell_disposable()
            if ok: return action
        
        if self.env.info_tk > 0:
            ok, action = self.__discard_probably_useless_card(0.0)
            if ok: return action
        else:
            ok, action = self.__tell_randomly()
            if ok: return action

class SearchAgent: #! Agent that performs 1-ply search
    
    def __init__(self, player_name, env: Hanabi):
        self.player_name = player_name
        self.env = env

        self.need_search = True

    def __sample_from_belief(self): 
        player_hands = {}
        for k in self.env.player_hands.keys():
            player_hands[k] = [Card(card.id, card.value, card.color) for card in self.env.player_hands[k]]
        id = 0 
        deck = [] # deck represents also our belief (i.e. as if cards of our hand are still in deck, we need to draw them)
        for _ in range(3):
            for color in ['red', 'yellow', 'green', 'blue', 'white']:
                deck.append(Card(id, 1, color)); id += 1
        for _ in range(2):
            for color in ['red', 'yellow', 'green', 'blue', 'white']:
                deck.append(Card(id, 2, color)); id += 1
        for _ in range(2):
            for color in ['red', 'yellow', 'green', 'blue', 'white']:
                deck.append(Card(id, 3, color)); id += 1
        for _ in range(2):
            for color in ['red', 'yellow', 'green', 'blue', 'white']:
                deck.append(Card(id, 4, color)); id += 1
        for color in ['red', 'yellow', 'green', 'blue', 'white']:
            deck.append(Card(id, 5, color)); id += 1
        
        for card in self.env.discard_pile:
            deck.remove(card)
        for k in COLORS:
            for card in self.env.table_cards[k]: deck.remove(card)
        for player in self.env.player_hands.keys():
            if player != self.player_name:
                for card in self.env.player_hands[player]: deck.remove(card)

        random.shuffle(deck)

        knowledge = [kn.copy() for kn in self.env.hands_knowledge[self.player_name]]
        for i, (c, v) in enumerate(knowledge):
            if c != '' and v == 0: # if I know only the color
                color_count = sum(1 for card in deck if card.color == c)
                if color_count == 1:
                    val = 0
                    for card in deck:
                        if card.color == c: val = card.value; break
                    knowledge[i] = [c,val]
            elif c == '' and v != 0: # if I know only the value
                value_count = sum(1 for card in deck if card.value == v)
                if value_count == 1:
                    col = ''
                    for card in deck:
                        if card.value == v: col = card.color; break
                    knowledge[i] = [col,v]
            #TODO: corner case in where in our belief only our ('',0) cards are left

        hand = []
        for c, v in knowledge:
            if c != '' and v != 0:
                for card in deck:
                    if card.color == c and card.value == v:
                        hand.append(card)
                        deck.remove(card)
                        break
            else:
                hand.append(None)

        for i, (c, v) in enumerate(knowledge):
            if hand[i] is None:
                if c != '':
                    for card in deck:
                        if card.color == c:
                            hand[i] = card
                            deck.remove(card)
                            break
                elif v != 0:
                    for card in deck:
                        if card.value == v:
                            hand[i] = card
                            deck.remove(card)
                            break

        for i, (c, v) in enumerate(knowledge):
            if hand[i] is None:
                hand[i] = deck.pop()
        if len(hand) < 5: print(len(hand), len(deck))
        player_hands[self.player_name] = hand
        return player_hands, deck

    def search(self):
        # Perform 1-ply search
        scores = {}
        # Need to sample the highest probable hand from belief space, and recompute the deck accordingly
        player_hands, deck = self.__sample_from_belief()
        valid_actions = self.env.valid_actions(self.player_name)
        
        for action in valid_actions:
            # For each action we do a rollout (according to blueprint strategy) and register the outcome
            simulation = Hanabi(self.player_name, self.env.num_players, player_hands, self.env.hands_knowledge, self.env.table_cards, 
                                self.env.discard_pile, deck, self.env.info_tk, self.env.err_tk, self.env.played_last_turn, self.env.play_order)
            agents = [SearchAgent(p, simulation) for p in self.env.play_order]
            simulation.step(self.player_name, action)
            
            done = simulation.is_final_state()
            while not done:
                for _ in range(simulation.num_players):
                    if self.need_search:
                        self.need_search = False
                        agents[simulation.player_idx].__act()
                    else: 
                        agents[simulation.player_idx].__act2(simulation)
                    done = simulation.is_final_state()
            
            key = [action['action']]
            if action['action'] == 'play' or action['action'] == 'discard':
                key.append(action['num'])
            else:
                key.append(action['type'])
                key.append(action['to'])
                key.append(action['value'])
            scores[tuple(key)] = simulation.final_score()
        
        return scores

    def __act2(self, env):
        a = Agent(self.player_name, env)
        a.act()
    
    def __act(self, card_thresh=35, num_simulations=1):
        if len(self.env.deck) < card_thresh:
            tot_scores = None
            for _ in range(num_simulations):
                scores = self.search()
                if tot_scores is None:
                    tot_scores = scores
                else:
                    for k in tot_scores.keys():
                        tot_scores[k] += scores[k]

            best_action, score = {}, 0
            for key in scores.keys():
                if scores[key] > score:
                    if key[0] == 'play' or key[0] == 'discard':
                        action, num = key
                        best_action = {'action': action, 'num': num}
                    else:
                        action, type, to, value = key
                        best_action = {'action': action, 'type': type, 'to': to, 'value': value}
                    score = scores[key]

            self.env.step(self.player_name, best_action)
        else:
            a = Agent(self.player_name, self.env)
            a.act()
        
class TechnicAngel:
    def __init__(self, ip=HOST, port=PORT, ID=0):
        self.s = None
        self.ID = ID
        if self.ID > 0:
            self.playerName = "technic_angel_" + str(self.ID)
        else:
            self.playerName = "technic_angel"

        self.statuses = ["Lobby", "Game", "GameHint"]
        self.game_ended = False
        self.status = self.statuses[0]
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        request = GameData.ClientPlayerAddData(self.playerName)
        self.s.connect((ip, port))
        self.s.send(request.serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerConnectionOk:
            print("Connection accepted by the server. Welcome " + self.playerName)
        stdout.flush()

        # color, value
        self.play_order = [self.playerName] # relative play order starting from me

        self.current_player = None
        self.player_hands = None
        self.hands_knowledge = None
        self.table_cards = None
        self.discard_pile = None
        self.used_note_tokens = None
        self.used_storm_tokens = None
        self.played_last_turn = None
        self.deck_has_cards = True

        self.final_score = None

        self.lock = Lock()
        self.cv = Condition()
        self.run = True
        
        #! Ready up your engines...
        input('Press [ENTER] to start...')
        #time.sleep(3)
        self.auto_ready()

        self.msg_queue = []
        self.t_listener = Thread(target=self.listener)
        self.t_listener.start()

        self.main_loop()

        with self.lock: 
            self.run = False
            self.s.shutdown(socket.SHUT_RDWR)
        self.t_listener.join()
        
    def __del__(self):
        if self.s is not None:
            self.s.close()

    def listener(self):
        try:
            while self.run:
                data = self.s.recv(DATASIZE)
                if not data: continue
                data = GameData.GameData.deserialize(data)
                with self.lock:
                    #! Insert in the msg queue just msgs to be processed, ignore the rest
                    accepted_types = type(data) is GameData.ServerGameStateData or \
                        type(data) is GameData.ServerGameOver or \
                        type(data) is GameData.ServerHintData  or \
                        type(data) is GameData.ServerActionValid or \
                        type(data) is GameData.ServerPlayerMoveOk or \
                        type(data) is GameData.ServerPlayerThunderStrike

                    if accepted_types: 
                        self.msg_queue.append(data)

                        if type(data) is not GameData.ServerGameStateData:
                            with self.cv: self.cv.notify_all()

        except ConnectionResetError: 
            with self.lock: self.game_ended = True
            with self.cv: self.cv.notify_all()
                
    def auto_ready(self):
        #! Send 'Ready' signal
        self.s.send(GameData.ClientPlayerStartRequest(self.playerName).serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerStartRequestAccepted:
            print("Ready: " + str(data.acceptedStartRequests) + "/"  + str(data.connectedPlayers) + " players")
            self.position = data.acceptedStartRequests - 1
            data = self.s.recv(DATASIZE)
            data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerStartGameData:
            print("Game start!")
            self.s.send(GameData.ClientPlayerReadyData(self.playerName).serialize())
            self.status = self.statuses[1]

    def consume_packets(self):
        read_pkts = []
        with self.lock:
            for data in self.msg_queue:

                # Discard data of other players
                if type(data) is GameData.ServerActionValid and data.player != self.playerName and data.action == 'discard':
                    for i, card in enumerate(self.player_hands[data.player]):
                        if card == data.card:
                            self.hands_knowledge[data.player].pop(i) 
                            self.hands_knowledge[data.player].append(['',0])
                            #if len(self.play_order) > 0: self.play_order.append(data.player)
                            break
                    read_pkts.append(data)

                # Play data of other players
                elif (type(data) is GameData.ServerPlayerMoveOk or \
                    type(data) is GameData.ServerPlayerThunderStrike) and data.player != self.playerName:
                    for i, card in enumerate(self.player_hands[data.player]):
                        if card == data.card:
                            self.hands_knowledge[data.player].pop(i)
                            self.hands_knowledge[data.player].append(['',0])
                            #if len(self.play_order) > 0: self.play_order.append(data.player)
                            break
                    read_pkts.append(data)

                # Hint data: I received a hint
                elif type(data) is GameData.ServerHintData and data.destination == self.playerName:
                    for i in data.positions: # indices in the current hand
                        if data.type == 'color':
                            self.hands_knowledge[self.playerName][i][0] = data.value
                        else:
                            self.hands_knowledge[self.playerName][i][1] = data.value
                    #if len(self.play_order) > 0: self.play_order.append(data.sender)        
                    read_pkts.append(data)

                # Hint data of other players
                elif type(data) is GameData.ServerHintData and data.destination != self.playerName:
                    for i in data.positions: # indices in the current hand
                        if data.type == 'color':
                            self.hands_knowledge[data.destination][i][0] = data.value
                        else:
                            self.hands_knowledge[data.destination][i][1] = data.value
                    #if len(self.play_order) > 0: self.play_order.append(data.sender)      
                    read_pkts.append(data)
                
                # Game over
                elif type(data) is GameData.ServerGameOver:
                    self.game_ended = True
                    self.final_score = data.score
                    read_pkts.append(data)
                
                elif type(data) is not GameData.ServerGameStateData:
                    read_pkts.append(data)

            for pkt in read_pkts:
                self.msg_queue.remove(pkt)

    def wait_for_turn(self):
        while self.current_player != self.playerName and not self.game_ended:
            with self.cv: self.cv.wait_for(lambda : False, timeout=0.1)
            self.consume_packets()
            if not self.game_ended: self.action_show()
        self.consume_packets()
        if not self.game_ended: self.action_show()
    
    def action_show(self):
        try: self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
        except ConnectionResetError: return
        found = False
        while not found:
            with self.lock:
                if self.game_ended: return
                read_pkts = []
                for data in self.msg_queue:
                    if type(data) is GameData.ServerGameStateData:
                        self.current_player = str(data.currentPlayer)
                        
                        self.player_hands = {self.playerName: []}
                        for player in data.players:
                            self.player_hands[player.name] = [Card(card.id, card.value, card.color) for card in player.hand]

                            if self.hands_knowledge is not None:
                                while len(self.player_hands[player.name]) < len(self.hands_knowledge[player.name]):
                                    self.deck_has_cards = False
                                    self.hands_knowledge[player.name].pop()
                            else:
                                self.play_order.append(player.name)

                        self.table_cards = { "red": [], "yellow": [], "green": [], "blue": [], "white": [] }
                        for k in data.tableCards.keys():
                            for card in data.tableCards[k]:
                                self.table_cards[k].append(Card(card.id, card.value, card.color))
                        self.discard_pile = []
                        for card in data.discardPile:
                            self.discard_pile.append(Card(card.id, card.value, card.color))
                        self.used_note_tokens = data.usedNoteTokens
                        self.used_storm_tokens = data.usedStormTokens
                        read_pkts.append(data)
                        found = True
                for pkt in read_pkts:
                    self.msg_queue.remove(pkt)
                        
    def action_discard(self, num):
        print('Discard', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Discard'
        assert self.used_note_tokens > 0, 'Cannot request a Discard when used_note_tokens == 0'
        assert num in range(len(self.player_hands.keys()))
        self.s.send(GameData.ClientPlayerDiscardCardRequest(self.playerName, num).serialize())
        self.hands_knowledge[self.playerName].pop(num)
        if self.__calc_real_deck_len() - 1 > 0:
            self.hands_knowledge[self.playerName].append(['',0])
        self.current_player = None

        #if len(self.play_order) == 0: self.play_order.append(self.playerName)
    
    def action_play(self, num):
        print('Play', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Play'
        assert num in range(len(self.player_hands.keys()))
        self.s.send(GameData.ClientPlayerPlayCardRequest(self.playerName, num).serialize())
        self.hands_knowledge[self.playerName].pop(num)
        if self.__calc_real_deck_len() - 1 > 0:
            self.hands_knowledge[self.playerName].append(['',0])
        self.current_player = None

        #if len(self.play_order) == 0: self.play_order.append(self.playerName)
    
    def action_hint(self, hint_type, dst, value):
        print('Hint', hint_type, dst, value)
        """
        hint_type = 'color' or 'value'
        dst = <player name> : str
        value = if 'color': ['red', 'yellow', 'green', 'blue', 'white'] else [1,2,3,4,5]
        """
        assert self.used_note_tokens < 8, 'Cannot Hint if all note tokens are used'
        assert hint_type in ['color', 'value'], 'hint_type can be "color" or "value"'
        assert dst in self.player_hands.keys() and dst != self.playerName, 'Passed the name of a non-existing player'
        if hint_type == 'color': assert value in ['red','yellow','green','blue','white']
        else: assert value in [1,2,3,4,5]
        self.s.send(GameData.ClientHintData(self.playerName, dst, hint_type, str(value)).serialize())
        for i in range(len(self.player_hands[dst])):
            if hint_type == 'color':
                if self.player_hands[dst][i].color == value:
                    self.hands_knowledge[dst][i][0] = value
            else:
                if self.player_hands[dst][i].value == value:
                    self.hands_knowledge[dst][i][1] = value

        self.current_player = None

        #if len(self.play_order) == 0: self.play_order.append(self.playerName)

    def __calc_real_deck_len(self):
        num_players = len(self.player_hands.keys())
        count = 5*num_players if num_players < 4 else 4*num_players
        for k in COLORS: count += len(self.table_cards[k])
        count += len(self.discard_pile)
        if 50 - count <= 0: self.deck_has_cards = False
        return max(50 - count, 0)
        
    def select_action(self):
        while True:
            id = 0 
            deck = []
            for _ in range(3):
                for color in ['red', 'yellow', 'green', 'blue', 'white']:
                    deck.append(Card(id, 1, color)); id += 1
            for _ in range(2):
                for color in ['red', 'yellow', 'green', 'blue', 'white']:
                    deck.append(Card(id, 2, color)); id += 1
            for _ in range(2):
                for color in ['red', 'yellow', 'green', 'blue', 'white']:
                    deck.append(Card(id, 3, color)); id += 1
            for _ in range(2):
                for color in ['red', 'yellow', 'green', 'blue', 'white']:
                    deck.append(Card(id, 4, color)); id += 1
            for color in ['red', 'yellow', 'green', 'blue', 'white']:
                deck.append(Card(id, 5, color)); id += 1
            
            for card in self.discard_pile:
                deck.remove(card)
            for k in COLORS:
                for card in self.table_cards[k]: deck.remove(card)
            for player in self.player_hands.keys():
                if player != self.playerName:
                    for card in self.player_hands[player]: deck.remove(card)

            simulation = Hanabi(self.playerName, len(self.player_hands.keys()), self.player_hands, 
                                self.hands_knowledge, self.table_cards, self.discard_pile, deck, self.used_note_tokens, 
                                self.used_storm_tokens, self.played_last_turn, self.play_order)
            agent = SearchAgent(self.playerName, simulation)
        
            try:
                action_scores = agent.search()
                best_action, score = None, 0
                for key in action_scores.keys():
                    if action_scores[key] > score or best_action is None:
                        if key[0] == 'play' or key[0] == 'discard':
                            action, num = key
                            best_action = {'action': action, 'num': num}
                        else:
                            action, type, to, value = key
                            best_action = {'action': action, 'type': type, 'to': to, 'value': value}
                        score = action_scores[key]
                if best_action['action'] == 'play':
                    self.action_play(best_action['num']); return
                elif best_action['action'] == 'discard':
                    self.action_discard(best_action['num']); return
                elif best_action['action'] == 'hint':
                    self.action_hint(best_action['type'], best_action['to'], best_action['value']); return
                assert False, "[PANIC]"
            except:
                continue

    def main_loop(self):
        #! Check how many cards in hand (4 or 5 depending on how many players)
        self.action_show()

        print(self.play_order)
        return

        len_hand = 0
        for key in self.player_hands.keys():
            if key != self.playerName:
                len_hand = len(self.player_hands[key])
                break
         
        self.hands_knowledge = {self.playerName: [['',0] for _ in range(len_hand)]}
        for player in self.player_hands.keys():
            self.hands_knowledge[player] = [['',0] for _ in range(len_hand)]
        self.played_last_turn = {k: False for k in self.player_hands.keys()}

        while True:
            self.wait_for_turn()
            if self.game_ended: break
            self.select_action()

        if self.final_score is not None:
            for c in COLORS:
                print(c[0], len(self.table_cards[c]), end=' | ')
            print()
            print(f'Final score: {self.final_score}/25')

ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
agent = TechnicAngel(ID=ID)