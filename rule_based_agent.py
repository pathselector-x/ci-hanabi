import numpy as np
import random
from hanabi import COLORS, Hanabi

class Agent:
    def __init__(self, player_idx: int, env: Hanabi):
        self.env = env
        self.pidx = player_idx

    def __play_probably_safe_card(self, threshold):
        knowledge = self.env.hands_knowledge[self.pidx]
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
                    if card[0] == c and card[1] == playable_val:
                        how_many -= 1
                    if card[0] == c: total -= 1

                for player in range(self.env.num_players):
                    if player != self.pidx:
                        for card in self.env.player_hands[player]:
                            if card[0] == c and card[1] == playable_val:
                                how_many -= 1
                            if card[0] == c: total -= 1

                p.append(how_many / total)
            
            elif v != 0:
                piles_playable = [k for k in COLORS if v == len(self.env.table_cards[k]) + 1]
                how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(piles_playable)
                total = (3 if v == 1 else (1 if v == 5 else 2)) * 5

                for card in self.env.discard_pile:
                    if card[0] in piles_playable and card[1] == v:
                        how_many -= 1
                    if card[1] == v: total -= 1

                for player in range(self.env.num_players):
                    if player != self.pidx:
                        for card in self.env.player_hands[player]:
                            if card[0] in piles_playable and card[1] == v:
                                how_many -= 1
                            if card[1] == v: total -= 1
                
                p.append(how_many / total)
            
            else:
                p.append(0.0)
                #min_p = 1.0
                #total = 50 - len(self.env.discard_pile) - \
                #    sum(len(self.env.table_cards[k]) for k in COLORS) - \
                #    len(self.env.player_hands[(self.pidx + 1)%2])
                #vals = {}
                #for k in COLORS:
                #    pv = len(self.env.table_cards[k]) + 1
                #    if pv > 5: continue
                #    if pv not in vals.keys(): vals[pv] = [k]
                #    else: vals[pv].append(k)
                #
                #for v in vals.keys():
                #    colors = vals[v]
                #    how_many = (3 if v == 1 else (1 if v == 5 else 2)) * len(colors)
                #    for card in self.env.discard_pile:
                #        if card[0] in colors and card[1] == v:
                #            how_many -= 1
                #    for player in range(self.env.num_players):
                #        if player != self.pidx:
                #            for card in self.env.player_hands[player]:
                #                if card[0] in colors and card[1] == v:
                #                    how_many -= 1
                #    min_p = min(min_p, how_many / total)
                #p.append(min_p)
        
        try:
            idx_to_play = np.argmax(p)
            if p[idx_to_play] >= threshold:
                return True, idx_to_play
            return False, None
        except:
            return False, None
    
    def __play_safe_card(self):
        ok, action = self.__play_probably_safe_card(1.0)
        if ok: return ok, action
        return False, None

    def __tell_anyone_about_useful_card(self):
        cnt = 0
        for pl in range(self.env.num_players):
            player = (self.pidx + pl) % self.env.num_players
            if player != self.pidx:
                hand = self.env.player_hands[player]
                kn = self.env.hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if len(self.env.table_cards[c]) + 1 == v:
                        if kc != '' and kv != 0: continue

                        if kc == '':
                            return True, 10 + COLORS.index(c) + 5 * cnt
                        
                        if kv == 0:
                            start_val = 10+5*(self.env.num_players-1)
                            return True, start_val + (v-1) + 5 * cnt
                cnt += 1
        return False, None

    def __interrupted_pile(self, color):
        for v in range(len(self.env.table_cards[color]) + 1, 6):
            count = 3 if v == 1 else (1 if v == 5 else 2)
            for card in self.env.discard_pile:
                if card[0] == color and card[1] == v:
                    count -= 1
            if count == 0: return True
        return False

    def __tell_dispensable(self):
        cnt = 0
        for pl in range(self.env.num_players): 
            player = (self.pidx + pl) % self.env.num_players
            if player != self.pidx:
                hand = self.env.player_hands[player]
                kn = self.env.hands_knowledge[player]

                for (kc, kv), (c, v) in zip(kn, hand):
                    if v <= len(self.env.table_cards[c]) and kv == 0:
                        start_val = 10+5*(self.env.num_players-1)
                        return True, start_val + (v-1) + 5 * cnt
                    elif len(self.env.table_cards[c]) == 5 and kc == '':
                        return True, 10 + COLORS.index(c) + 5 * cnt
                    elif self.__interrupted_pile(c) and kc == '':
                        return True, 10 + COLORS.index(c) + 5 * cnt
                cnt += 1
        return False, None
    
    def __osawa_discard(self):
        kn = self.env.hands_knowledge[self.pidx]

        for i, (c, v) in enumerate(kn):
            if c != '' and v != 0:
                if v <= len(self.env.table_cards[c]):
                    return True, 5 + i
                elif len(self.env.table_cards[c]) == 5:
                    return True, 5 + i
                elif self.__interrupted_pile(c):
                    return True, 5 + i 
            elif c != '':
                if len(self.env.table_cards[c]) == 5:
                    return True, 5 + i
                elif self.__interrupted_pile(c):
                    return True, 5 + i
            elif v != '': #! Happy incident, should be 'v != 0' but it works better like this IDK
                if all(v <= len(self.env.table_cards[k]) for k in COLORS):
                    return True, 5 + i

        return False, None

    def __discard_probably_useless_card(self, threshold):
        kn = self.env.hands_knowledge[self.pidx]
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
                        if card[0] == c and card[1] <= v_lte:
                            how_many -= 1
                        if card[0] == c: total -= 1
                    for player in range(self.env.num_players):
                        if player != self.pidx:
                            for card in self.env.player_hands[player]:
                                if card[0] == c and card[1] <= v_lte:
                                    how_many -= 1
                                if card[0] == c: total -= 1
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
                        if card[0] in colors and card[1] == v:
                            how_many -= 1
                        if card[1] == v: total -= 1
                    for player in range(self.env.num_players):
                        if player != self.pidx:
                            for card in self.env.player_hands[player]:
                                if card[0] in colors and card[1] == v:
                                    how_many -= 1
                                if card[1] == v: total -= 1
                    p.append(how_many / total)
            else:
                p.append(0.0)
        try:
            idx_to_discard = np.argmax(p)
            if all(pv == p[0] for pv in p): idx_to_discard = 0
            if p[idx_to_discard] >= threshold:
                return True, 5 + idx_to_discard
            return False, None
        except:
            return False, None
    
    def __discard_oldest_first(self):
        return True, 5

    def __tell_randomly(self):
        legal_actions = self.env.compute_actions(self.pidx)
        legal_actions = [a for a in legal_actions if a >= 10]
        action = random.choice(legal_actions)
        return True, action
    
    def act(self, execute_action=True):
        if self.env.err_tk < 2 and len(self.env.deck) == 0:
            ok, action = self.__play_probably_safe_card(0.0)
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action
        
        ok, action = self.__play_safe_card()
        if ok: 
            if execute_action: self.env.step(self.pidx, action)
            return action

        if self.env.err_tk < 3:
            ok, action = self.__play_probably_safe_card(0.7)
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action

        if self.env.info_tk < 8:
            ok, action = self.__tell_anyone_about_useful_card()
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action

        if self.env.info_tk > 4 and self.env.info_tk < 8:
            ok, action = self.__tell_dispensable()
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action
        
        if self.env.info_tk > 0:
            ok, action = self.__osawa_discard()
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action
            ok, action = self.__discard_probably_useless_card(0.0)
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action
            ok, action = self.__discard_oldest_first()
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action
        else:
            ok, action = self.__tell_randomly()
            if ok: 
                if execute_action: self.env.step(self.pidx, action)
                return action

        assert False, f'PANIC!!! {self.env.info_tk}'

#import matplotlib.pyplot as plt
#def eval_agent_goodness(num_agents=2, num_games=1000):
#    env = Hanabi(num_players=num_agents)
#    players = []
#    for i in range(num_agents):
#        players.append(Agent(i, env))
#
#    stats = []
#
#    for game in range(num_games):
#        env.reset()
#        done = False
#        while not done:
#            for p in players:
#                p.act()
#                if env.err_tk == 3 or all(env.played_last_turn) or sum(len(env.table_cards[k]) for k in COLORS) == 25:
#                    done = True
#                    break
#
#        if env.err_tk < 3:
#            stats.append(sum(len(env.table_cards[k]) for k in COLORS))
#        else:
#            stats.append(0)
#
#        if game % 1000 == 0: print(game)
#
#    print(f'Average score on {num_games} games: {sum(stats) / num_games}')
#    print(f'Max score: {max(stats)} (in {sum(1 for s in stats if s == max(stats))}/{num_games} games)')
#    print(f'Lost {sum(1 for s in stats if s == 0)}/{num_games} games')
#    plt.hist(stats, bins=25, edgecolor='white', linewidth=1.2)
#    plt.show()
#    exit()
#
##eval_agent_goodness(num_agents=2, num_games=1000)