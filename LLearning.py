from multiprocessing import Process, Manager
from server import manageNetwork
from agent import TechnicAngel
import time

def f(idx):
    agent = TechnicAngel('127.0.0.1', 1024, idx)
    #if agent.final_score is not None:
    #    return_dict['final_score'] = agent.final_score 
    #else:
    #    return_dict['final_score'] = 0

if __name__ == '__main__':

    num_games = 5
    score_tot = 0

    for _ in range(num_games):
        print(_)

        #manager = Manager()
        #return_dict = manager.dict()

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
    
    print(score_tot / num_games)

        