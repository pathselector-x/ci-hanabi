from hanabi import Hanabi, COLORS
from test_bench import Agent
from itertools import product
import random

FULL_DECK = [(c,v) for c,v in product(COLORS, [1,1,1,2,2,3,3,4,4,5])] # can use .copy()

class SASAgent:
    def __init__(self, player_idx, env: Hanabi):
        self.player_idx = player_idx
        self.env = env
        #self.need_search = True
    
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
        
        #assert len(knowledge) == len(self.env.player_hands[self.player_idx])
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
        #!print('Sampled: ', player_hands)
        valid_actions = self.env.compute_actions(self.player_idx)

        for action in valid_actions:
            # For each action we do a rollout (according to blueprint strategy) and register the outcome
            simulation = Hanabi(self.env.num_players)
            simulation.set_state(self.env.hands_knowledge, self.env.table_cards, self.env.discard_pile, self.env.info_tk, self.env.err_tk, player_hands, deck, self.env.played_last_turn)
            agents = [Agent(p, simulation) for p in range(simulation.num_players)]
            simulation.step(self.player_idx, action)
            #self.need_search = False
            
            done = simulation.is_final_state()
            while not done:
                for p in range(simulation.num_players):
                    player = (self.player_idx + 1 + p) % simulation.num_players
                    #if agents[player].need_search:
                    #    agents[player].act()
                    #else: 
                    agents[player].act()#simulation)
                    done = simulation.is_final_state()
            scores[action] = simulation.final_score()
        
        return scores
        
    #def act2(self, env):
    #    a = Agent(self.player_idx, env)
    #    a.act()

    def act(self, card_thresh=39, num_simulations=1):
        if len(self.env.deck) < card_thresh:
            tot_scores = None
            for _ in range(num_simulations):
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

            #self.env.step(self.player_idx, best_action)
            return best_action
        else:
            a = Agent(self.player_idx, self.env)
            action = a.act(execute_action=False)
            return action

import matplotlib.pyplot as plt

def eval_agent_goodness(num_agents=2, num_games=1000):
    env = Hanabi(num_players=num_agents)
    thresh = 50 - num_agents * 5 - 1
    if num_agents > 3: thresh = 50 - num_agents * 4 - 1
    print('Thresh: ', thresh)
    players = []
    for i in range(num_agents):
        players.append(SASAgent(i, env))

    stats = []

    for game in range(num_games):
        env.reset(0)
        done = False
        while not done:
            for p in players:
                action = p.act(card_thresh=thresh, num_simulations=1)
                env.step(p.player_idx, action)
                if env.is_final_state(): 
                    done = True
                    break

        if env.err_tk < 3:
            stats.append(sum(len(env.table_cards[k]) for k in COLORS))
        else:
            stats.append(0)

        if game % (num_games//10) == 0: print(game)

    print(f'Average score on {num_games} games: {sum(stats) / num_games}')
    print(f'Max score: {max(stats)} (in {sum(1 for s in stats if s == max(stats))}/{num_games} games)')
    print(f'Lost {sum(1 for s in stats if s == 0)}/{num_games} games')
    plt.hist(stats, bins=25, edgecolor='white', linewidth=1.2)
    plt.show()
    exit()

#eval_agent_goodness(num_agents=2, num_games=10)
#stats = []
#num_agents = 2
#num_games = 100
#count = num_games
## 20, 10: 19.87
## 50, 10: 21.47
## 20, 20: 20.83
## 20, 50: 21.60 Best so far
## 50, 50: bad
## 30, 50: 
#while count > 0:
#    try:
#        print(num_games - count)
#        env = Hanabi(num_agents, verbose=(num_games == 1))
#        env.reset(0)
#
#        agents = [SASAgent(i, env) for i in range(num_agents)]
#        done = False
#        while not done:
#            for a in agents:
#                a.act(card_thresh=35, num_simulations=1) # 35 1
#                if env.is_final_state(): done = True; break
#
#        if env.err_tk < 3:
#            stats.append(sum(len(env.table_cards[k]) for k in COLORS))
#        else:
#            stats.append(0)
#
#        print(f'\nCards left: {len(env.deck)}')
#        print(f'Error tokens: {3 - env.err_tk} | Info tokens: {8 - env.info_tk}')
#        for k in COLORS:
#            print(f'{k}: {len(env.table_cards[k])} | ', end='')
#        print()
#        count -= 1
#    except Exception as e:
#        if type(e) == KeyboardInterrupt: break
#        continue
#
#if num_games > 1:    
#    print(f'Average score on {num_games} games: {sum(stats) / num_games}')
#    print(f'Max score: {max(stats)} (in {sum(1 for s in stats if s == max(stats))}/{num_games} games)')
#    print(f'Lost {sum(1 for s in stats if s == 0)}/{num_games} games')
#    plt.hist(stats, bins=25, edgecolor='white', linewidth=1.2)
#    plt.show()