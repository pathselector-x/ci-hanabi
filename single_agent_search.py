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

        hand = [] #TODO: sample according to knowledge !!!
        for _ in self.env.hands_knowledge[self.player_idx]:
            hand.append(deck.pop())

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
        
        best_action, score = 0, 0
        for key in scores.keys():
            if scores[key] > score:
                best_action = key
                score = scores[key]
        return best_action

    def act(self):
        action = self.__search()
        self.env.step(self.player_idx, action)

env = Hanabi(2, verbose=True)
env.reset(0)

p1 = SASAgent(0, env)
p2 = SASAgent(0, env)

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