from multiprocessing import Process, Manager
from threading import Thread
from server import manageNetwork
from agent import TechnicAngel
import time
import matplotlib.pyplot as plt

def f(idx, ):
    agent = TechnicAngel(ID=idx)
    
    #if agent.final_score is not None:
    #    return_dict['final_score'] = agent.final_score 
    #else:
    #    return_dict['final_score'] = 0

if __name__ == '__main__':

    num_games = 100
    score_tot = 0

    #manager = Manager()
    #return_dict = manager.dict()
    #return_dict['rew'] = []

    for game in range(num_games):
        print(f'\033[93mGame #{game+1}\033[0m')

        process_server = Process(target=manageNetwork)
        process_server.start()

        process_agents = []
        for i in range(2):
            p = Process(target=f, args=(i,))
            p.start()
            process_agents.append(p)
        
        process_server.join()
        process_agents[0].join()
        process_agents[1].join()

        #score_tot += return_dict['final_score']
    
    #print(score_tot / num_games)


        