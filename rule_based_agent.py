from sys import argv, stdout
from threading import Thread, Lock, Condition
import GameData
import socket
from constants import *

from game import Card, Player

COLORS = ['red','yellow','green','blue','white']
VALUES = range(1,5+1)
# enum
NO = 0
MAYBE = 1
YES = 2

#! SmartBot implementation
# Credits: https://github.com/Quuxplusone/Hanabi
class CardKnowledge:
    def __init__(self, bot):
        self.bot_ = bot
        self.cantBe_ = {k: [False for _ in range(5+1)] for k in COLORS}
        self.possibilities_ = -1
        self.color_ = ''
        self.value_ = -2
        self.playable_ = MAYBE
        self.valuable_ = MAYBE
        self.worthless_ = MAYBE
        self.probabilityPlayable_ = -1.0
        self.probabilityValuable_ = -1.0
        self.probabilityWorthless_ = -1.0

    def copy(self):
        kn = CardKnowledge(self.bot_)
        kn.cantBe_ = {k: [False for _ in range(5+1)] for k in COLORS}
        for k in COLORS:
            for v in VALUES:
                kn.cantBe_[k][v] = self.cantBe_[k][v]
        kn.possibilities_ = self.possibilities_
        kn.color_ = self.color_
        kn.value_ = self.value_
        kn.playable_ = self.playable_
        kn.valuable_ = self.valuable_
        kn.worthless_ = self.worthless_
        kn.probabilityPlayable_ = self.probabilityPlayable_ 
        kn.probabilityValuable_ = self.probabilityValuable_ 
        kn.probabilityWorthless_ = self.probabilityWorthless_
        return kn

    def mustBe(self, color=None, value=None):
        self.computeIdentity()
        if self.color is not None:
            return self.color_ == color
        elif self.value is not None:
            return self.value_ == value

    def cannotBe(self, color=None, value=None):
        if color is not None and value is not None:
            return self.cantBe_[color][value]
        elif color is not None:
            if self.color_ != '': return self.color_ != color
            for v in VALUES:
                if not self.cantBe_[color][v]: return False
            return True
        elif value is not None:
            if self.value_ >= 0: return self.value_ != value
            for k in COLORS:
                if not self.cantBe_[k][value]: return False
            return True

    def setMustBe(self, color=None, value=None):
        if color is not None and value is not None:
            for k in COLORS:
                for v in VALUES:
                    self.cantBe_[k][v] = not (k == color and v == value)
            self.possibilities_ = -1
            self.color_ = color
            self.value_ = value
            if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
            if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
            if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0
        elif color is not None:
            for k in COLORS:
                for v in VALUES:
                    if k != color: self.cantBe_[k][v] = True
            self.possibilities_ = -1
            self.color_ = color
            if self.value_ == -1: self.value_ = -2
            if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
            if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
            if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0
        elif value is not None:
            for k in COLORS:
                for v in VALUES:
                    if v != value: self.cantBe_[k][v] = True
            self.possibilities_ = -1
            if self.color_ == '-1': self.color_ = ''
            self.value_ = value
            if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
            if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
            if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0

    def setCannotBe(self, color=None, value=None): 
        if color is not None:
            for v in VALUES:
                self.cantBe_[color][v] = True
            self.possibilities_ = -1
            if self.color_ == '-1': self.color_ = ''
            if self.value_ == -1: self.value_ = -2
            if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
            if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
            if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0
        elif value is not None:
            for k in COLORS:
                self.cantBe_[k][value] = True
            self.possibilities_ = -1
            if self.color_ == '-1': self.color_ = ''
            if self.value_ == -1: self.value_ = -2
            if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
            if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
            if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0

    def setIsPlayable(self, knownPlayable): 
        for k in COLORS:
            playableValue = len(self.bot_.table_cards[k]) + 1
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                if (v == playableValue) != knownPlayable:
                    self.cantBe_[k][v] = True
        self.possibilities_ = -1
        if self.color_ == '-1': self.color_ = ''
        if self.value_ == -1: self.value_ = -2
        self.playable_ = YES if knownPlayable else NO
        self.probabilityPlayable_ = 1.0 if knownPlayable else 0.0
        if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
        if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0
        if knownPlayable: 
            self.worthless_ = NO
            self.probabilityWorthless_ = 0.0

    def setIsValuable(self, knownValuable): 
        for k in COLORS:
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                if self.bot_.isValuable(k,v) != knownValuable:
                    self.cantBe_[k][v] = True
        self.possibilities_ = -1
        if self.color_ == '-1': self.color_ = ''
        if self.value_ == -1: self.value_ = -2
        if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
        self.valuable_ = YES if knownValuable else NO
        self.probabilityValuable_ = 1.0 if knownValuable else 0.0
        if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0
        if knownValuable: 
            self.worthless_ = NO
            self.probabilityWorthless_ = 0.0

    def setIsWorthless(self, knownWorthless):
        for k in COLORS:
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                if self.bot_.isWorthless(k,v) != knownWorthless:
                    self.cantBe_[k][v] = True
        self.possibilities_ = -1
        if self.color_ == '-1': self.color_ = ''
        if self.value_ == -1: self.value_ = -2
        if self.playable_ == MAYBE: self.probabilityPlayable_ = -1.0
        if self.valuable_ == MAYBE: self.probabilityValuable_ = -1.0
        self.worthless_ = YES if knownWorthless else NO
        self.probabilityWorthless_ = 1.0 if knownWorthless else 0.0
        if self.worthless_ == MAYBE: self.probabilityWorthless_ = -1.0
        if knownWorthless: 
            self.playable_ = NO
            self.valuable_ = NO
            self.probabilityPlayable_ = 0.0
            self.probabilityValuable_ = 0.0

    def befuddleByDiscard(self): 
        if self.worthless_ != YES:
            self.valuable_ = MAYBE
            self.probabilityValuable_ = -1.0
        if self.worthless_ != YES:
            self.worthless_ = MAYBE
            self.probabilityWorthless_ = -1.0

    def befuddleByPlay(self, success): 
        if success:
            self.playable_ = MAYBE
            self.probabilityPlayable_ = -1.0
        else:
            self.valuable_ = MAYBE
            self.probabilityValuable_ = -1.0
        if self.worthless_ != YES:
            self.worthless_ = MAYBE
            self.probabilityWorthless_ = -1.0

    def update(self, useMyEyesight): 
        if not self.known():
            recompute = False
            for k in COLORS:
                for v in VALUES:
                    if self.cantBe_[k][v]: continue
                    total = (3 if v == 1 else (1 if v == 5 else 2))
                    played = self.bot_.playedCount_[k][v]
                    held = self.bot_.eyesightCount_[k][v] if useMyEyesight else self.bot_.locatedCount_[k][v]
                    assert played + held <= total
                    if played + held == total:
                        self.cantBe_[k][v] = True
                        recompute = True
            if recompute:
                self.possibilities_ = -1
                self.color_ = ''
                self.value_ = -2
                self.playable_, self.valuable_, self.worthless_ = MAYBE, MAYBE, MAYBE
                self.probabilityPlayable_, self.probabilityValuable_, self.probabilityWorthless_ = -1.0, -1.0, -1.0

    def known(self):
        self.computeIdentity()
        return self.color_ != -1 and self.value_ != -1
    
    def color(self):
        self.computeIdentity()
        return self.color_

    def value(self):
        self.computeIdentity()
        return self.value_
    
    def knownCard(self):
        assert self.known()
        return Card(0, self.value_, self.color_)

    def possibilities(self):
        self.computePossibilities()
        return self.possibilities_
    
    def playable(self):
        self.computePlayable()
        return self.playable_
    
    def valuable(self):
        self.computeValuable()
        return self.valuable_

    def worthless(self):
        self.computeWorthless()
        return self.worthless_
    
    def probabilityPlayable(self):
        self.computePlayable()
        return self.probabilityPlayable_
    
    def probabilityValuable(self):
        self.computeValuable()
        return self.probabilityValuable_
    
    def probabilityWorthless(self):
        self.computeWorthless()
        return self.probabilityWorthless_

    def couldBePlayableWithValue(self, value): 
        if value < 1 or 5 < value or self.cannotBe(value=value): return False
        if self.playable() != MAYBE: return False
        kn = self.copy()
        kn.setMustBe(value=value)
        return kn.playable() != NO

    def couldBeValuableWithValue(self, value):
        if value < 1 or 5 < value or self.cannotBe(value=value): return False
        if self.valuable() != MAYBE: return False
        kn = self.copy()
        kn.setMustBe(value=value)
        return kn.valuable() != NO

    def computeIdentity(self): 
        if self.color_ != '' and self.value_ != -2: return
        color = ''
        value = -2
        for k in COLORS:
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                color = k if (color == '' or color == k) else '-1'
                value = v if (value == -2 or value == v) else -1
        assert color != ''
        assert value != -2
        self.color_ = color
        self.value_ = value

    def computePossibilities(self): 
        if self.possibilities_ != -1: return
        possibilities = 0
        for k in COLORS:
            for v in VALUES:
                if not self.cantBe_[k][v]:
                    possibilities += 1
        assert possibilities >= 1
        self.possibilities_ = possibilities

    def computePlayable(self): 
        if self.probabilityPlayable_ != -1.0: return
        total_count = 0
        yes_count = 0
        for k in COLORS:
            playableValue = len(self.bot_.table_cards[k]) + 1
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                total_count += 1
                if v == playableValue:
                    yes_count += 1
        assert total_count >= 1
        self.probabilityPlayable_ = yes_count / total_count
        self.playable_ = YES if (yes_count == total_count) else (MAYBE if yes_count != 0 else NO)

    def computeValuable(self): 
        if self.probabilityValuable_ != -1.0: return
        total_count = 0
        yes_count = 0
        for k in COLORS:
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                total_count += 1
                if v == self.bot_.isValuable(k,v):
                    yes_count += 1
        assert total_count >= 1
        self.probabilityValuable_ = yes_count / total_count
        self.valuable_ = YES if (yes_count == total_count) else (MAYBE if yes_count != 0 else NO)

    def computeWorthless(self): 
        if self.probabilityWorthless_ != -1.0: return
        total_count = 0
        yes_count = 0
        for k in COLORS:
            for v in VALUES:
                if self.cantBe_[k][v]: continue
                total_count += 1
                if v == self.bot_.isWorthless(k,v):
                    yes_count += 1
        assert total_count >= 1
        self.probabilityWorthless_ = yes_count / total_count
        self.worthless_ = YES if (yes_count == total_count) else (MAYBE if yes_count != 0 else NO)

class Hint:
    def __init__(self, type, val, fitness, to):
        self.type = type
        self.value = val
        self.fitness = fitness
        self.to = to

    def includes(self, color, value):
        if self.type == 'color':
            return self.value == color
        else:
            return self.value == value

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
        self.current_hand_knowledge = None #! Holds knowledge about current hand
        self.already_hinted = None #! Holds knowledge about already hinted cards (col, val)

        self.current_player = None
        self.player_hands = None
        self.table_cards = None
        self.discard_pile = None
        self.used_note_tokens = None
        self.used_storm_tokens = None

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
                    done_removing = False
                    for p in self.player_hands:
                        if p.name == data.player:
                            for i, card in enumerate(p.hand):
                                if card == data.card:
                                    self.hand_knowledge[p.name].pop(i)
                                    self.hand_knowledge[p.name].append(CardKnowledge(self))
                                    self.already_hinted[p.name].pop(i)
                                    self.already_hinted[p.name].append([False, False])
                                    done_removing = True
                                    break
                            if done_removing: break
                    read_pkts.append(data)

                # Play data of other players
                elif (type(data) is GameData.ServerPlayerMoveOk or \
                    type(data) is GameData.ServerPlayerThunderStrike) and data.player != self.playerName:
                    done_removing = False
                    for p in self.player_hands:
                        if p.name == data.player:
                            for i, card in enumerate(p.hand):
                                if card == data.card:
                                    self.hand_knowledge[p.name].pop(i)
                                    self.hand_knowledge[p.name].append(CardKnowledge(self))
                                    self.already_hinted[p.name].pop(i)
                                    self.already_hinted[p.name].append([False, False])
                                    done_removing = True
                                    break
                            if done_removing: break
                    read_pkts.append(data)

                # Hint data: I received a hint
                elif type(data) is GameData.ServerHintData and data.destination == self.playerName:
                    for i in data.positions: # indices in the current hand
                        #self.current_hand_knowledge[i][0 if data.type == 'color' else 1] = str(data.value)
                        if data.type == 'color':
                            self.hand_knowledge[self.playerName][i].setMustBe(color=data.value)
                        else:
                            self.hand_knowledge[self.playerName][i].setMustBe(value=data.value)
                    read_pkts.append(data)

                # Hint data of other players
                elif type(data) is GameData.ServerHintData and data.destination != self.playerName:
                    for i in data.positions: # indices in the current hand
                        self.already_hinted[data.destination][i][0 if data.type == 'color' else 1] = True
                        if data.type == 'color':
                            self.hand_knowledge[data.destination][i].setMustBe(color=data.value)
                        else:
                            self.hand_knowledge[data.destination][i].setMustBe(value=data.value)
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
                        self.player_hands = []
                        for player in data.players:
                            pl = Player(player.name)
                            for card in player.hand:
                                pl.hand.append(Card(card.id, card.value, card.color))
                            self.player_hands.append(pl)
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
        assert num in range(0, self.myHandSize_)
        self.s.send(GameData.ClientPlayerDiscardCardRequest(self.playerName, num).serialize())
        self.hand_knowledge[self.playerName].pop(num)
        self.hand_knowledge[self.playerName].append(CardKnowledge(self))
        self.current_player = None
    
    def action_play(self, num):
        print('Play', num)
        """num = [0, len(hand)-1]: int"""
        assert self.current_player == self.playerName, 'Be sure it is your turn, before requesting a Play'
        assert num in range(0, self.myHandSize_)
        self.s.send(GameData.ClientPlayerPlayCardRequest(self.playerName, num).serialize())
        self.hand_knowledge[self.playerName].pop(num)
        self.hand_knowledge[self.playerName].append(CardKnowledge(self))
        self.current_player = None
    
    def action_hint(self, hint_type, dst, value):
        print('Hint', hint_type, dst, value)
        """
        hint_type = 'color' or 'value'
        dst = <player name> : str
        value = if 'color': ['red', 'yellow', 'green', 'blue', 'white'] else [1,2,3,4,5]
        """
        assert self.used_note_tokens < 8, 'Cannot Hint if all note tokens are used'
        assert hint_type in ['color', 'value'], 'hint_type can be "color" or "value"'
        assert dst in [p.name for p in self.player_hands], 'Passed the name of a non-existing player'
        if hint_type == 'color': assert value in ['red','yellow','green','blue','white']
        else: assert value in [1,2,3,4,5]
        self.s.send(GameData.ClientHintData(self.playerName, dst, hint_type, value).serialize())
        for player in self.player_hands:
            if player == dst:
                for i, card in enumerate(self.player_hands):
                    if hint_type == 'color' and card.color == value:
                        self.hand_knowledge[dst][i].setMustBe(color=card.color)
                    elif hint_type == 'value' and card.value == value:
                        self.hand_knowledge[dst][i].setMustBe(value=card.value)
        self.current_player = None

    def calc_deck(self):
        deck = {} #! Holds knowledge about unseen cards
        cards_in_deck = 50 #! How many cards are left in the deck
        for col in ['red','yellow','green','blue','white']:
            deck[(col,'1')] = 3
            deck[(col,'2')] = 2
            deck[(col,'3')] = 2
            deck[(col,'4')] = 2
            deck[(col,'5')] = 1

        for player in self.player_hands:
            for card in player.hand:
                deck[(str(card.color), str(card.value))] -= 1
                cards_in_deck -= 1

        for col in ['red','yellow','green','blue','white']:
            for card in self.table_cards[col]:
                deck[(str(card.color), str(card.value))] -= 1
                cards_in_deck -= 1

        for card in self.discard_pile:
            deck[(str(card.color), str(card.value))] -= 1
            cards_in_deck -= 1
        
        for card in self.current_hand_knowledge:
            c, v = card
            if c != '' and v != '':
                deck[(c,v)] -= 1
            cards_in_deck -= 1

        return deck, cards_in_deck

    def select_action(self): #! Logic
        cardsRemainingInDeck = 50 - self.myHandSize_ * len(self.player_hands)
        for _ in self.discard_pile:
            cardsRemainingInDeck -= 1
        for k in COLORS:
            cardsRemainingInDeck -= len(self.table_cards[k])

        if cardsRemainingInDeck == 0:
            if self.maybePlayLowestPlayableCard(): return
            if self.maybePlayMisteryCard(): return
        if self.maybeGiveValuableWarning(): return
        if self.maybeDiscardFinesse(): return
        if self.maybePlayLowestPlayableCard(): return
        if self.maybeGiveHelpfulHint(): return
        if self.maybePlayMisteryCard(): return

        if self.used_note_tokens == 0: 
            #TODO more than 2 players!!
            self.action_hint('value', self.player_hands[0].name, self.player_hands[0].hand[0].value)
        else:
            if self.maybeDiscardWorthlessCard(): return
            if self.maybeDiscardOldCard(): return
            
            best_index = 0
            for i in range(self.myHandSize_):
                if self.hand_knowledge[self.playerName][i].value() > self.hand_knowledge[self.playerName][best_index].value():
                    best_index = i
            self.action_discard(best_index)
    
    def isPlayable(self, color, value): 
        playableValue = len(self.table_cards[color]) + 1
        return value == playableValue

    def isValuable(self, color, value): 
        card_count = (3 if value == 1 else (1 if value == 5 else 2))
        if self.playedCount_[color][value] != card_count - 1: return False
        return not self.isWorthless(color, value)

    def isWorthless(self, color, value):
        playableValue = len(self.table_cards[color]) + 1
        if value < playableValue: return True
        while value > playableValue:
            value -= 1
            card_count = (3 if value == 1 else (1 if value == 5 else 2))
            if self.playedCount_[color][value] == card_count: return True
        return False

    def updateEyesightCount(self): pass
    def updateLocatedCount(self): pass
    def invalidateKnol(self, player_index, card_index, draw_new_card): pass
    def seePublicCard(self): pass

    def nextDiscardIndex(self, to): 
        if to != self.playerName: # it means 'to' is an idx
            to = self.player_hands[to].name
        best_fitness = 0
        best_index = -1
        for i in range(self.myHandSize_):
            if self.hand_knowledge[to][i].playable() == YES: return -1
            if self.hand_knowledge[to][i].worthless() == YES: return -1
            if self.hand_knowledge[to][i].valuable() == YES: continue

            fitness = 100 + self.hand_knowledge[to][i].probabilityWorthless()
            if fitness > best_fitness:
                best_fitness = fitness
                best_index = i
        return best_index

    def noValuableWarningWasGiven(self, from_): pass

    def bestHintForPlayer(self, partner):
        is_really_playable = [card.value == len(self.table_cards[card.color]) + 1 for card in self.player_hands[partner].hand]
        valueToAvoid = -1
        #TODO: more than 2 players
        discardIndex = self.nextDiscardIndex(partner)
        if discardIndex != -1:
            valueToAvoid = self.player_hands[partner].hand[discardIndex].value
            if not self.hand_knowledge[self.player_hands[partner].name][discardIndex].couldBeValuableWithValue(valueToAvoid):
                valueToAvoid = -1
        def is_ok(hint, oldKnols, newKnols):
            if hint.value != -1 and hint.value == valueToAvoid: return False
            reveals_a_playable_card = False
            is_misleading = MAYBE
            for i in range(self.myHandSize_-1, -1, -1):
                if oldKnols[i].playable() != MAYBE: continue
                if newKnols[i].playable() == YES:
                    reveals_a_playable_card = True
                elif newKnols[i].playable() == MAYBE and hint.includes(self.player_hands[partner].hand):
                    if is_misleading == MAYBE:
                        is_misleading = NO if is_really_playable else YES
            if reveals_a_playable_card or is_misleading == NO: return True
            else: return False
        return self.bestHintForPlayerGivenConstraint(partner, is_ok)

    def reduction_in_entropy(self, oldKnols, newKnols):
        result = 0
        for i in range(len(oldKnols)):
            result += oldKnols[i].possibilities() - newKnols[i].possibilities()
        return result

    def bestHintForPlayerGivenConstraint(self, to, is_okay):
        colors = {k: False for k in COLORS}
        values = {v: False for v in VALUES}
        for card in self.player_hands[to].hand:
            colors[card.color] = True
            values[card.value] = True
        oldKnols = [kn.copy() for kn in self.hand_knowledge[self.player_hands[to].name]]
        best = Hint('color', 'red', -10, self.player_hands[to].name)
        for k in COLORS:
            if k not in colors.keys(): continue
            hint = Hint('color', k, -1, self.player_hands[to].name)
            newKnols = [kn.copy() for kn in oldKnols]
            for i in range(self.myHandSize_):
                if self.player_hands[to].hand[i].color == k:
                    newKnols[i].setMustBe(color=k)
                else:
                    newKnols[i].setCannotBe(color=k)
            if is_okay(hint, oldKnols, newKnols):
                hint.fitness = self.reduction_in_entropy(oldKnols, newKnols)
                if hint.fitness > best.fitness:
                    best = hint
        for v in VALUES:
            if v not in values.keys(): continue
            hint = Hint('value', v, -1, self.player_hands[to].name)
            newKnols = [kn.copy() for kn in oldKnols]
            for i in range(self.myHandSize_):
                if self.player_hands[to].hand[i].value == v:
                    newKnols[i].setMustBe(value=v)
                else:
                    newKnols[i].setCannotBe(value=v)
            if is_okay(hint, oldKnols, newKnols):
                hint.fitness = self.reduction_in_entropy(oldKnols, newKnols)
                if hint.fitness > best.fitness:
                    best = hint
        return best

    def vector_count(self, vec, value):
        result = 0
        for i in range(len(vec)):
            if vec[i] == value: result += 1
        return result

    def maybeDiscardFinesse(self): 
        if self.used_note_tokens == 0: return False

        myPlayableCards = []
        myPlayableIndices = []

        for i in range(self.myHandSize_):
            kn = self.hand_knowledge[self.playerName][i]
            if kn.known() and kn.valuable() == NO and kn.playable() == YES:
                myPlayableCards.append(kn.knownCard())
                myPlayableIndices.append(i)
        
        if len(myPlayableCards) == 0: return False

        othersNewestCards = []

        for player in self.player_hands:
            for i in range(self.myHandSize_-1, -1, -1):
                othersNewestCards.append(player.hand[i])
        
        for j in range(len(myPlayableCards)):
            if self.vector_count(othersNewestCards, myPlayableCards[j]) == 1:
                self.action_discard(myPlayableIndices[j])
                return True
        return False

    def maybePlayLowestPlayableCard(self): 
        best_index = -1
        best_fitness = 0
        for i in range(self.myHandSize_):
            if self.hand_knowledge[self.playerName][i].playable() == NO: continue
            self.hand_knowledge[self.playerName][i].update(True)
            if self.hand_knowledge[self.playerName][i].playable() != YES: continue
            fitness = 6 - self.hand_knowledge[self.playerName][i].value()
            if self.hand_knowledge[self.playerName][i].playable() != YES: fitness += 100
            if fitness > best_fitness:
                best_index = i
                best_fitness = fitness
        if best_index != -1:
            self.action_play(best_index)
            return True
        return False

    def maybeGiveHelpfulHint(self): 
        if self.used_note_tokens == 8: return False
        bestHint = None
        #TODO more than 2 players (start with the following player)
        for i in range(len(self.player_hands)):
            candidate = self.bestHintForPlayer(i)
            if bestHint is None or candidate.fitness > bestHint.fitness:
                bestHint = candidate
        if bestHint.fitness <= 0: return False
        self.action_hint(bestHint.type, bestHint.to, bestHint.value)
        return True

    def maybeGiveValuableWarning(self): 
        if self.used_note_tokens == 8: return False
        player_to_warn = 0 # idx #TODO more than 2 players !!!
        discardIndex = self.nextDiscardIndex(player_to_warn)
        if discardIndex == -1: return False
        targetCard = self.player_hands[player_to_warn].hand[discardIndex]
        if not self.isValuable(targetCard.color, targetCard.value): return False
        bestHint = self.bestHintForPlayer(player_to_warn)
        if bestHint.fitness > 0:
            self.action_hint(bestHint.type, self.player_hands[player_to_warn].name, bestHint.value)
            return True
        self.action_hint('value', self.player_hands[player_to_warn].name, targetCard.value)
        return True

    def maybePlayMisteryCard(self): 
        best_fitness = 0
        best_index = -1
        for i in range(self.myHandSize_-1, -1, -1):
            self.hand_knowledge[self.playerName][i].update(True)
            if self.hand_knowledge[self.playerName][i].playable() == MAYBE:
                fitness = self.hand_knowledge[self.playerName][i].probabilityPlayable()
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_index = i
        if best_index != -1:
            self.action_play(best_index)
            return True
        return False

    def maybeDiscardWorthlessCard(self): 
        best_index = -1
        best_fitness = 0
        for i in range(self.myHandSize_):
            if self.hand_knowledge[self.playerName][i].worthless() == NO: continue
            if self.hand_knowledge[self.playerName].worthless() == MAYBE:
                self.hand_knowledge[self.playerName][i].update(True)
                if self.hand_knowledge[self.playerName][i].worthless() != YES: continue
            fitness = 2.0 - self.hand_knowledge[self.playerName][i].probabilityWorthless()
            if fitness > best_fitness:
                best_index = i
                best_fitness = fitness
        if best_index != -1:
            self.action_discard(best_index)
            return True
        return False

    def maybeDiscardOldCard(self): 
        best_index = self.nextDiscardIndex(self.playerName)
        if best_index != -1:
            self.action_discard(best_index)
            return True
        return False

    def main_loop(self):
        #! Check how many cards in hand (4 or 5 depending on how many players)
        self.action_show()

        self.hand_knowledge = {} # Keep track of what you know about your hand
        self.hand_knowledge[self.playerName] = []
        for _ in range(len(self.player_hands[0].hand)):
            self.hand_knowledge[self.playerName].append(CardKnowledge(self)) # color, value
        for player in self.player_hands:
            for _ in range(len(self.player_hands[0].hand)):
                self.hand_knowledge[player.name].append(CardKnowledge(self)) # color, value

        self.myHandSize_ = len(self.player_hands[0].hand)
        self.playedCount_ = {k: [0 for _ in range(5+1)] for k in COLORS} # what cards have been played so far
        self.locatedCount_ = {k: [0 for _ in range(5+1)] for k in COLORS} # what cards in players' hands are definitely identified
        self.eyesightCount_ = {k: [0 for _ in range(5+1)] for k in COLORS} # what cards in players' hand are visible to me
        
        self.already_hinted = {} # Keep track of already hinted cards
        for p in self.player_hands:
            self.already_hinted[p.name] = [[False, False] for _ in range(len(self.player_hands[0].hand))] # color, value

        #for player in self.player_hands:
        #    print(player.name)

        while True:
            self.wait_for_turn()
            if self.game_ended: break
            self.select_action()

        if self.final_score is not None:
            for c in COLORS:
                print(c[0], len(self.table_cards[c]), end=' | ')
            print()
            print(f'Final score: {self.final_score}/25')

#ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
#agent = TechnicAngel(ID=ID)