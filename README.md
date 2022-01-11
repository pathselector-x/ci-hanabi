# HANABI AGENT - Leonardo Iurada (s291018)
Computational Intelligence A.A. 2021/2022 - Politecnico di Torino

# Agent
Implemented in file **_agent.py_**. To run it, start the server and then type in a shell:
```bash
python3 agent.py
```

# Hanabi rules
Setup:
- 50 cards (5 suits: R, G, B, Y, W):
    - 3 cards with value 1
    - 2 cards with value 2
    - 2 cards with value 3
    - 2 cards with value 4
    - 1 cards with value 5
- 8 info tokens
- 3 error tokens

Each player has:
- 5 cards if there are 2 or 3 players
- 4 cards if there are 4 or 5 players
- Players can NOT see their cards, but can see the cards of the other players

Players have 3 actions in their turn:
- Provide a HINT (if there are info tokens) to another player about 1 VALUE or 1 SUIT of cards held by that player. This action consumes 1 info token
- Discard a card (if < 8 info tokens, put the card in the discard pile and add 1 info token back. Draw a new card)
- Play a card (if the played card doesn't start a new sequence or doesn't continue any sequence, remove 1 error token, put the played card in the discard pile. Draw a new card)

Checking the firework display:
- 1 card for each suit (5 piles total)
- cards shall be in rising order (from 1 to 5)

The game ends:
- if you completed 5 fireworks
- if error tokens == 0
- if there is no card to play

Scores:
- completed fireworks * 5 + max value of last firework (if not completed)
- 0 if error tokens == 0

### Goal
Write a client (agent) that learns how to play Hanabi.

## Server

The server accepts passing objects provided in GameData.py back and forth to the clients.
Each object has a ```serialize()``` and a ```deserialize(data: str)``` method that must be used to pass the data between server and client.

Watch out! I'd suggest to keep everything in the same folder, since serialization looks dependent on the import path (thanks Paolo Rabino for letting me know).

Commands for server:

+ exit: exit from the server

## Client

Commands for client:

+ exit: exit from the game
+ ready: set your status to ready (lobby only)
+ show: show cards
+ hint \<type> \<destinatary> \<value>:
  + type: 'color' or 'value'
  + destinatary: name of the person you want to ask the hint to
  + value: 
    + if type is 'color', then value is one of these: \['red', 'yellow', 'green', 'white', 'blue']
    + if type is 'value', then value is a number between 1 and 5 (included)
+ discard \<num>: discard the card *num* (\[0-4]) from your hand
+ play \<num>: play the card *num* (\[0-4]) from your hand