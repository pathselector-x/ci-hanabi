from sys import argv, stdout
from threading import Thread, Lock, Condition
import select
import GameData
import socket
from constants import *
import os
from collections import deque

from game import Game

class TechnicAngel:
    def __init__(self, ip=HOST, port=PORT, ID=0):
        self.statuses = ["Lobby", "Game", "GameHint"]
        self.status = self.statuses[0]
        if ID > 0:
            self.playerName = "technic_angel_" + str(ID)
        else:
            self.playerName = "technic_angel"
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        request = GameData.ClientPlayerAddData(self.playerName)
        self.s.connect((ip, port))
        self.s.send(request.serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerConnectionOk:
            print("Connection accepted by the server. Welcome " + self.playerName)
        stdout.flush()

        self.lock = Lock()
        self.run = True
        
        self.current_player = None
        self.player_hands = None
        self.table_cards = None
        self.discard_pile = None
        self.used_note_tokens = None
        self.used_storm_tokens = None
        
        # Ready up your engines...
        self.main_loop()

    def __del__(self):
        self.s.close()

    def listener(self):
        while self.run:
            data = self.s.recv(DATASIZE)
            if not data: continue
            data = GameData.GameData.deserialize(data)
            with self.lock: 
                accepted_types = type(data) is GameData.ServerGameStateData
                if accepted_types: self.msg_queue.append(data)

            #if type(data) is GameData.ServerGameStateData:
            #    self.current_player = data.currentPlayer
            #    self.player_hands = data.players
            #    self.table_cards = data.tableCards
            #    self.discard_pile = data.discardPile
            #    self.used_note_tokens = data.usedNoteTokens
            #    self.used_storm_tokens = data.usedStormTokens
            #if type(data) is GameData.ServerActionInvalid:
            #    print("Invalid action performed. Reason:")
            #    print(data.message)
            #if type(data) is GameData.ServerActionValid:
            #    print("Action valid!")
            #    print("Current player: " + data.player)
            #if type(data) is GameData.ServerPlayerMoveOk:
            #    print("Nice move!")
            #    print("Current player: " + data.player)
            #if type(data) is GameData.ServerPlayerThunderStrike:
            #    print("OH NO! The Gods are unhappy with you!")
            #if type(data) is GameData.ServerHintData:
            #    if data.destination == self.playerName:
            #        print("Hint type: " + data.type)
            #        print("Your cards with value " + str(data.value) + " are:")
            #        for i in data.positions:
            #            print("\t" + str(i))
            #return

    def auto_ready(self):
        # Send Ready signal
        self.s.send(GameData.ClientPlayerStartRequest(self.playerName).serialize())
        data = self.s.recv(DATASIZE)
        data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerPlayerStartRequestAccepted:
            print("Ready: " + str(data.acceptedStartRequests) + "/"  + str(data.connectedPlayers) + " players")
            data = self.s.recv(DATASIZE)
            data = GameData.GameData.deserialize(data)
        if type(data) is GameData.ServerStartGameData:
            print("Game start!")
            self.s.send(GameData.ClientPlayerReadyData(self.playerName).serialize())
            self.status = self.statuses[1]

    def query_game_info(self):
        self.s.send(GameData.ClientGetGameStateRequest(self.playerName).serialize())
        while True:
            with self.lock:
                for data in self.msg_queue:
                    if type(data) is GameData.ServerGameStateData:
                        self.current_player = data.currentPlayer
                        self.player_hands = data.players
                        self.table_cards = data.tableCards
                        self.discard_pile = data.discardPile
                        self.used_note_tokens = data.usedNoteTokens
                        self.used_storm_tokens = data.usedStormTokens
                        self.msg_queue.remove(data)
                        return

    def main_loop(self):
        self.auto_ready()
        
        self.msg_queue = deque([])
        self.t_listener = Thread(target=self.listener)
        self.t_listener.start()

        self.query_game_info()
        print(self.current_player)
        for player in self.player_hands:
            print(player.name)
            for card in player.hand:
                print(card.value, card.color)
        print(self.table_cards)

        with self.lock: self.run = False
        print('joining listener...')
        self.t_listener.join()

        print('Exiting...')

ID = int(argv[1]) if int(argv[1]) in [1,2,3,4,5] else 0
agent = TechnicAngel(ID=ID)
