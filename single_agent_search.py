from hanabi import Hanabi, COLORS
from test_bench import Agent
from itertools import product
import random

FULL_DECK = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])] # can use .copy()

class SASAgent:
    def __init__(self, player_idx, env: Hanabi):
        self.player_idx = player_idx
        self.env = env
    
    def __sample_from_belief(self):
        player_hands = [h.copy() for h in self.env.player_hands]
        deck = FULL_DECK.copy() # deck represents also our belief (i.e. as if cards of our hand are still in deck, we need to draw them)
        for p in range(self.env.num_players):
            if p != self.player_idx:
                for card in self.env.player_hands[p]: deck.remove(card)
        for card in self.env.discard_pile: deck.remove(card)
        for k in COLORS:
            for card in self.env.table_cards[k]: deck.remove(card)

        random.shuffle(deck)

        knowledge = self.env.hands_knowledge[self.player_idx].copy()
        for i, (c, v) in enumerate(knowledge):
            if c != '' and v == 0: # if I know only the color
                color_count = sum(1 for card in deck if card[0] == c)
                if color_count == 1:
                    val = 0
                    for card in deck:
                        if card[0] == c: val = card[1]; break
                    knowledge[i] = (c,val)
            elif c == '' and v != 0: # if I know only the value
                value_count = sum(1 for card in deck if card[1] == v)
                if value_count == 1:
                    col = ''
                    for card in deck:
                        if card[1] == v: col = card[0]; break
                    knowledge[i] = (col,v)
            #TODO: corner case in where in our belief only our ('',0) cards are left

        hand = []
        for c, v in knowledge:
            if c != '' and v != 0:
                for card in deck:
                    if card[0] == c and card[1] == v:
                        hand.append(card)
                        deck.remove(card)
                        break
            else:
                hand.append(None)

        for i, (c, v) in enumerate(knowledge):
            if hand[i] is None:
                if c != '':
                    for card in deck:
                        if card[0] == c:
                            hand[i] = card
                            deck.remove(card)
                            break
                elif v != 0:
                    for card in deck:
                        if card[1] == v:
                            hand[i] = card
                            deck.remove(card)
                            break

        for i, (c, v) in enumerate(knowledge):
            if hand[i] is None:
                hand[i] = deck.pop()

        player_hands[self.player_idx] = hand
        return player_hands, deck

    def __search(self):
        # Perform 1-ply search
        scores = {}
        # Need to sample the highest probable hand from belief space, and recompute the deck accordingly
        player_hands, deck = self.__sample_from_belief()
        valid_actions = self.env.compute_actions(self.player_idx)

        for action in valid_actions:
            # For each action we do a rollout (according to blueprint strategy) and register the outcome
            simulation = Hanabi(self.env.num_players)
            simulation.set_state(self.env.hands_knowledge, self.env.table_cards, self.env.discard_pile, self.env.info_tk, self.env.err_tk, player_hands, deck, self.env.played_last_turn)
            agents = [Agent(p, simulation) for p in range(simulation.num_players)]
            simulation.step(self.player_idx, action)
            
            done = simulation.is_final_state()
            while not done:
                for p in range(simulation.num_players):
                    player = (self.player_idx + 1 + p) % simulation.num_players
                    agents[player].act()
                    done = simulation.is_final_state()
            scores[action] = simulation.final_score()
        
        return scores
        

    def act(self):
        if len(self.env.deck) < 40:
            tot_scores = None
            for _ in range(25):
                scores = self.__search()
                if tot_scores is None:
                    tot_scores = scores
                else:
                    for k in tot_scores.keys():
                        tot_scores[k] += scores[k]

            best_action, score = 0, 0
            for key in scores.keys():
                if scores[key] > score:
                    best_action = key
                    score = scores[key]

            self.env.step(self.player_idx, best_action)
        else:
            a = Agent(self.player_idx, self.env)
            a.act()

env = Hanabi(2, verbose=True)
env.reset(0)

p1 = SASAgent(0, env)
p2 = SASAgent(1, env)

while True:
    p1.act()
    if env.is_final_state(): break
    p2.act()
    if env.is_final_state(): break

print(f'\nCards left: {len(env.deck)}')
print(f'Error tokens: {3 - env.err_tk} | Info tokens: {8 - env.info_tk}')
for k in COLORS:
    print(f'{k}: {len(env.table_cards[k])} | ', end='')
print()