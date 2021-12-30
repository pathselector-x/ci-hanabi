from torch import nn
import torch
from collections import deque
import itertools
import numpy as np
import random
import time
import matplotlib.pyplot as plt

import gym

#! Test DQN agent for simple task

class GridWorld:

    def __init__(self):
        self.state = [3,2]
        self.grid = np.array([
            [1,0,2,0],
            [1,1,1,1],
            [1,1,0,1],
            [0,1,1,0]])
        self.rewards = np.array([
            [1,-10,100,-10],
            [1,10,20,1],
            [1,5,-10,1],
            [-10,3,0,-10]])
    
    def step(self, action):
        x, y = self.state
        if action == 0: # left
            if y - 1 < 0 or self.grid[x, y - 1] == 0: return self.state, -10, 1
            self.state[1] -= 1
            
        elif action == 1: # right
            if y + 1 > self.grid.shape[0]-1 or self.grid[x, y + 1] == 0: return self.state, -10, 1
            self.state[1] += 1
        elif action == 2: # up
            if x - 1 < 0 or self.grid[x - 1, y] == 0: return self.state, -10, 1
            self.state[0] -= 1
        elif action == 3: # down
            if x + 1 > self.grid.shape[1]-1 or self.grid[x + 1, y] == 0: return self.state, -10, 1
            self.state[0] += 1
        return self.state, self.rewards[self.state[0], self.state[1]], 1 if self.grid[self.state[0], self.state[1]] == 2 else 0

    def reset(self):
        self.state = [3,2]
        return self.state

    def render(self):
        time.sleep(0.3)
        for i in range(4):
            for j in range(4):
                if i == self.state[0] and j == self.state[1]: print('X', end=' ')
                elif self.grid[i,j] == 1: print('_', end=' ')
                elif self.grid[i,j] == 0: print(' ', end=' ')
                elif self.grid[i,j] == 2: print('O', end=' ')
            print()
        print()
 
GAMMA = 0.99
BATCH_SIZE = 32
BUFFER_SIZE = 50000
MIN_REPLAY_SIZE = 1000
EPSILON_START = 1.0
EPSILON_END = 0.2
EPSILON_DECAY = 10000
TARGET_UPDATE_FREQ = 10000

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
env = gym.make('CartPole-v0')

loss_array = []

class DQN(nn.Module):
    def __init__(self, env):
        super(DQN, self).__init__()
        in_features = int(np.prod(env.observation_space.shape))

        ff_layers = [nn.Linear(in_features, 64), nn.ReLU()]
        for _ in range(3):
            ff_layers.append(nn.Linear(64,64))
            ff_layers.append(nn.ReLU())
        self.net = nn.Sequential(*ff_layers)

        self.lstm = nn.LSTMCell(64, 64).to(device)

        self.fc_a = nn.Linear(64, env.action_space.n)
    
    def forward(self, x):
        x = self.net(x)
        o, _ = self.lstm(x)
        return self.fc_a(o)
    
    def act(self, obs):
        obs_t = torch.as_tensor(obs, dtype=torch.float32, device=device)
        q_values = self(obs_t.unsqueeze(0))
        max_q_index = torch.argmax(q_values, dim=1)[0]
        action = max_q_index.detach().item()
        return action

replay_buffer = deque(maxlen=BUFFER_SIZE)
rew_buffer = deque([0.0], maxlen=100)

episode_reward = 0.0

online_net = DQN(env).to(device)
target_net = DQN(env).to(device)

target_net.load_state_dict(online_net.state_dict())

optimizer = torch.optim.Adam(online_net.parameters(), lr=0.001)

#! Init replay buffer
obs = env.reset()
for _ in range(MIN_REPLAY_SIZE):
    action = env.action_space.sample() #random.choice([0,1,2,3]) # Random action
    new_obs, rew, done, _ = env.step(action)
    transition = (obs, action, rew, done, new_obs)
    replay_buffer.append(transition)
    obs = new_obs

    if done:
        obs = env.reset()

#! Main Training loop
obs = env.reset()

for step in itertools.count():
    epsilon = np.interp(step, [0, EPSILON_DECAY], [EPSILON_START, EPSILON_END])

    if random.random() <= epsilon:
        action = env.action_space.sample() #random.choice([0,1,2,3]) # Random action
    else:
        action = online_net.act(obs) #! ONLINE
    
    new_obs, rew, done, _ = env.step(action)
    transition = (obs, action, rew, done, new_obs)
    replay_buffer.append(transition)
    obs = new_obs

    episode_reward += rew

    if done:
        obs = env.reset()
        rew_buffer.append(episode_reward)
        episode_reward = 0.0

    # Start Gradient Step
    transitions = random.sample(replay_buffer, BATCH_SIZE)

    obses = np.asarray([t[0] for t in transitions])
    actions = np.asarray([t[1] for t in transitions])
    rews = np.asarray([t[2] for t in transitions])
    dones = np.asarray([t[3] for t in transitions])
    new_obses = np.asarray([t[4] for t in transitions])

    obses_t = torch.as_tensor(obses, dtype=torch.float32, device=device)
    actions_t = torch.as_tensor(actions, dtype=torch.int64, device=device).unsqueeze(-1)
    rews_t = torch.as_tensor(rews, dtype=torch.float32, device=device).unsqueeze(-1)
    dones_t = torch.as_tensor(dones, dtype=torch.float32, device=device).unsqueeze(-1)
    new_obses_t = torch.as_tensor(new_obses, dtype=torch.float32, device=device)

    # Compute targets
    target_q_values = target_net(new_obses_t) #! TARGET
    max_target_q_values = target_q_values.max(dim=1, keepdim=True)[0]

    targets = rews_t + GAMMA * (1 - dones_t) * max_target_q_values

    # Compute Loss 
    q_values = online_net(obses_t) #! ONLINE

    action_q_values = torch.gather(input=q_values, dim=1, index=actions_t)

    loss = nn.functional.smooth_l1_loss(action_q_values, targets)
    loss_array.append([step, loss])

    # After solved, watch it play
    if len(rew_buffer) >= 1:
        if np.mean(rew_buffer) >= 190:
            loss_array = np.array(loss_array)
            plt.plot(loss_array[:,0], loss_array[:,1])
            plt.show()
            obs = env.reset()
            while True:
                env.render()
                action = online_net.act(obs)
                obs, _, done, _ = env.step(action)
                if done:
                    obs = env.reset()

    # Gradient Descent
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    # Update Target Network
    if step % TARGET_UPDATE_FREQ == 0:
        target_net.load_state_dict(online_net.state_dict())

    # Logging
    if step % 1000 == 0:
        print()
        print(f'Step {step} | Avg Rew: {np.mean(rew_buffer)}')