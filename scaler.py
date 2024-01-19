import docker
import requests
import time


MONITOR_TIME = 20 # monitor response times over 20 seconds
SCALE_UP_THRESHOLD = 10 # add more resources if response time > 10 seconds
SCALE_DOWN_THRESHOLD = 5 # decrease resources if respone time < 5 seconds

'''
looking at the compose file
cpu: 0.25, memory: 256M

from the cybera dashboard our machines specs are:
Flavor Name
2gb ram, 2vcpu, 20gb disk

by cpu: 2/0.25 = 8 replicas
by memory: 2000/256 = 7.8 replicas, we can round down cuz other overhead like OS so 7 replicas max

'''
MAX_REPLICAS = 7
MIN_REPLICAS = 1
web_microservice = "http://10.2.7.79:8000/"
service_id = "tjevoqetz0nd" # from sudo docker service ls we can see the ids


client = docker.from_env()
# source: https://docker-py.readthedocs.io/en/stable/services.html
service = client.services.get(service_id) # returns type service

def get_average_response_time():
    
    start_time = time.time()
    response_times = []

    # while time elapsed is less than 20 seconds
    while time.time() - start_time < MONITOR_TIME:
        t0 = time.time()
        requests.get(web_microservice)
        t1 = time.time()
        response_time = t1 - t0
        response_times.append(response_time)
        print(response_time)
    
    average_response_time = sum(response_times) / len(response_times)

    print(f"Average Response Time over {MONITOR_TIME} seconds: {average_response_time}")
    return average_response_time


# TODO: scale factor?? i guess if time is like double the threshold we can scale twice??
def scale(num_replicas):
    service.scale(num_replicas) # scale the webapp_web service
    return

def main():
    return
    


get_average_response_time()

# if __name__ == '__main__':
    