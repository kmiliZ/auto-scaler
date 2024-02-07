import docker
import requests
import time
from flask import Flask, render_template,make_response
from redis import Redis
import threading
import plotly.express as px
import json
import math

redis = Redis(host='10.2.7.79', port=6379,decode_responses=True)
start_time = time.time()

app = Flask(__name__)


MONITOR_TIME = 20 # monitor response times over 20 seconds
SCALE_UP_THRESHOLD = 10 # add more resources if response time > 15 seconds
SCALE_DOWN_THRESHOLD = 5 # decrease resources if response time < 5 seconds
MAX_REPLICAS = 15
MIN_REPLICAS = 1
web_service_url = "http://10.2.7.79:8000/"
web_service_id = "tjevoqetz0nd" # from sudo docker service ls we can see the ids
swarm_manager_ip = '10.2.7.79'
flask_port = '5001'

class DockerClient:
    def __init__(self):
        self.client = docker.from_env()

    # returns service object
    def get_service(self, service_id):
        return self.client.services.get(service_id)


class Service:
    def __init__(self, service_id, service_url, docker_client):
        self.docker_client = docker_client
        # service object as decescribed by  https://docker-py.readthedocs.io/en/stable/services.html
        self.service_id = service_id
        self.service = self.docker_client.get_service(service_id) 
        self.name = self.service.name
        self.service_url = service_url


    # we need to always get the updated service. when we make the changes stuff like the version number might change
    # we will get a docker api error if the service is not up to date
    def update(self):
        self.service = self.docker_client.get_service(self.service_id)

    def get_current_replicas(self):
        # attrs returns a dictionary. Follow the nested keys to get the replicas
        self.update()
        return self.service.attrs["Spec"]["Mode"]["Replicated"]["Replicas"]


    def scale(self, num_replicas):
        self.update()
        self.service.scale(num_replicas)

    def get_url(self):
        self.update()
        return self.service_url
    
    def get_name(self):
        self.update()
        return self.name

class Autoscaler:
    def __init__(self, service, monitor_time, scale_up_threshold, scale_down_threshold, max_replicas, min_replicas):
        self.service = service
        self.monitor_time = monitor_time
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.max_replicas = max_replicas
        self.min_replicas = min_replicas
        self.last_scale = 0

    def get_average_response_time(self):
        print("Getting average response time...")
        start_time = time.time()
        response_times = []

        # while time elapsed is less than 20 seconds
        while time.time() - start_time < self.monitor_time:
            t0 = time.time()

            try:
                response = requests.get(self.service.get_url(), timeout=self.monitor_time) 
                t1 = time.time()
                response_time = t1 - t0
                response_times.append(response_time)
                print(response_time)
            except requests.exceptions.Timeout:
                print("Request timed out.")
                # treat as very long response time
                return self.monitor_time
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
                continue
    
            average_response_time = sum(response_times) / len(response_times)

        # average_response_time = 1
        print(f"Average Response Time over {MONITOR_TIME} seconds: {average_response_time}")
        return average_response_time

    def redis_get_avg_response_time(self):
        newest_value = redis.lindex('avg_response_t', 0)

        if newest_value:
            last_avg_t = float(newest_value)
        else:
            last_avg_t = 0
        return last_avg_t

    def get_scale_up_factor(self,average_response_time):
        last_avg_t = self.redis_get_avg_response_time()
        diff = last_avg_t - average_response_time

        # if self.last_scale = 0: 
        #     return 1
        
        # if self.last_scale > 0:
        #     diff = average_response_time - last_avg_t
            
        #     # if diff > 0: # not improved at all (or for dramatic increase?)
        #     #     scale = self.last_scale + 2
        #     # else:
        #     scale = self.last_scale + 1
        # elif self.last_scale < 0:
        #     scale = abs(math.ceil(diff/4))
        # else:
        #     scale = 1
        scale = math.ceil(average_response_time/self.scale_up_threshold)
        return scale

    def get_scale_down_factor(self,average_response_time):
        last_avg_t = self.redis_get_avg_response_time()
        diff = last_avg_t - average_response_time


        # if self.last_scale < 0:
        #     # if diff > 0:
        #     #     scale = self.last_scale -2
        #     # else:
        #     scale = self.last_scale -1
        # elif self.last_scale < 0:
        #     scale = -math.ceil(diff/4)
        # else:
        #     scale = -1
        scale = -math.ceil(average_response_time/self.scale_down_threshold)
        return scale

    def perform_scaling(self):
        average_response_time = self.get_average_response_time()
        current_replicas = self.service.get_current_replicas()
        new_replicas = current_replicas
        scale = 0

            # we want to scale up and we can
        if average_response_time >= self.scale_up_threshold and current_replicas < self.max_replicas:
            scale = self.get_scale_up_factor(average_response_time)
                
            print("scale: ",scale)
            print("last_scale:",self.last_scale)
            new_replicas = min(current_replicas + scale, self.max_replicas)
            self.service.scale(new_replicas)
            print(f'Scaled up {self.service.get_name()} to {new_replicas} replicas.')
        
        # we want to scale up but we are at max
        elif average_response_time >= self.scale_up_threshold and current_replicas == self.max_replicas:
            print("Reached max replicas can't scale up")

        # we want to scale down and we can
        elif average_response_time <= self.scale_down_threshold and current_replicas > self.min_replicas:
            scale = self.get_scale_down_factor(average_response_time)

            new_replicas = max(current_replicas + scale,self.min_replicas)
            print("scale down to:to {new_replicas} replicas")
            self.service.scale(new_replicas)
            print(f'Scaled down {self.service.get_name()} to {new_replicas} replicas.')

        elif average_response_time <= self.scale_down_threshold and current_replicas == self.min_replicas:
            print("Reached min replicas cant scale down")
        
        else:
            print(f'Did not scale {self.service.get_name()}. Response time within threshold')
        
        print("scale: ",scale)
        print("last_scale:",self.last_scale)
        self.last_scale = scale
        # for the visualizer
        global tare

        redis.lpush('avg_response_t', average_response_time)
        redis.lpush('size',new_replicas)

        redis.lpush('time_series', time.time()-start_time)
        hits = int(redis.get('hits'))
        redis.lpush('loads',hits - tare)
        tare = hits


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template("index.html")

@app.route('/data', methods=['GET', 'POST'])
def data():
    replicas_count = redis.lrange('size',0,-1)
    avg_response_time = redis.lrange('avg_response_t',0,-1)
    load = redis.lrange('loads',0,-1)
    time_series = redis.lrange('time_series',0,-1)

    data = [{'time':time_series ,'a':avg_response_time,'l':load,'r':replicas_count}]
    response = make_response(json.dumps(data))
    response.content_type = 'application/json'
    return response

    
def flask_app():
    app.run(host='0.0.0.0', port=5001)

if __name__ == '__main__':
    docker_client = DockerClient()
    web_service = Service(web_service_id, web_service_url, docker_client) 
    print("Service url: ", web_service.get_url())
    autoscaler = Autoscaler(web_service, MONITOR_TIME, SCALE_UP_THRESHOLD, SCALE_DOWN_THRESHOLD, MAX_REPLICAS, MIN_REPLICAS)
    current_replicas = autoscaler.service.get_current_replicas()
    redis.delete('avg_response_t')
    redis.delete('size')
    redis.delete('time_series') # maybe we could use a better time_series idk
    
    redis.lpush('size',current_replicas)
    redis.lpush('time_series', 0)
    global tare
    tare = int(redis.get('hits'))


    thread = threading.Thread(target = flask_app)
    thread.start()

    while True:
        autoscaler.perform_scaling()
        time.sleep(5) # forthe scaling to finish
