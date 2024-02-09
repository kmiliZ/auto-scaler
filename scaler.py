import docker
import requests
import time
from flask import Flask, render_template,make_response
from redis import Redis
import threading
import plotly.express as px
import json
import math
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Use environment variables
REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
WEB_SERVICE_URL = os.getenv('WEB_SERVICE_URL', 'http://127.0.0.1:8000/')
WEB_SERVICE_ID = os.getenv('WEB_SERVICE_ID', 'default_id')
SWARM_MANAGER_IP = os.getenv('SWARM_MANAGER_IP', '127.0.0.1')
FLASK_PORT = os.getenv('FLASK_PORT', '5001')
MONITOR_TIME = int(os.getenv('MONITOR_TIME', 30))
SCALE_UP_THRESHOLD = int(os.getenv('SCALE_UP_THRESHOLD', 15))
SCALE_DOWN_THRESHOLD = int(os.getenv('SCALE_DOWN_THRESHOLD', 5))
MAX_REPLICAS = int(os.getenv('MAX_REPLICAS', 15))
MIN_REPLICAS = int(os.getenv('MIN_REPLICAS', 1))

redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
start_time = time.time()

app = Flask(__name__)

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

        # while time elapsed is less than monitor time
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

        print(f"Average Response Time over {MONITOR_TIME} seconds: {average_response_time}")
        return average_response_time

    def get_scale_up_factor(self,average_response_time):
        scale = math.ceil(average_response_time/self.scale_up_threshold)
        return scale

    def get_scale_down_factor(self,average_response_time):
        scale = -math.ceil(self.scale_down_threshold/average_response_time)
        return scale

    def perform_scaling(self):
        average_response_time = self.get_average_response_time()
        current_replicas = self.service.get_current_replicas()
        new_replicas = current_replicas
        scale = 0

            # we want to scale up and we can
        if average_response_time >= self.scale_up_threshold and current_replicas < self.max_replicas:
            scale = self.get_scale_up_factor(average_response_time)
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
            self.service.scale(new_replicas)
            print(f'Scaled down {self.service.get_name()} to {new_replicas} replicas.')

        elif average_response_time <= self.scale_down_threshold and current_replicas == self.min_replicas:
            print("Reached min replicas cant scale down")
        
        else:
            print(f'Did not scale {self.service.get_name()}. Response time within threshold')
        
        # for the plot visualizer
        redis.lpush('size',new_replicas)
        redis.lpush('time_series', time.time()-start_time)

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template("index.html")

@app.route('/data', methods=['GET', 'POST'])
def data():
    replicas_count = redis.lrange('size',0,-1)
    time_series = redis.lrange('time_series',0,-1)

    data = [{'time':time_series ,'r':replicas_count}]
    response = make_response(json.dumps(data))
    response.content_type = 'application/json'
    return response

    
def flask_app():
    app.run(host='0.0.0.0', port=5001)

if __name__ == '__main__':
    docker_client = DockerClient()
    web_service = Service(WEB_SERVICE_ID, WEB_SERVICE_URL, docker_client)  
    print("Service url: ", web_service.get_url())
    autoscaler = Autoscaler(web_service, MONITOR_TIME, SCALE_UP_THRESHOLD, SCALE_DOWN_THRESHOLD, MAX_REPLICAS, MIN_REPLICAS)
    current_replicas = autoscaler.service.get_current_replicas()
    redis.delete('size')
    redis.delete('time_series') 
    
    redis.lpush('size',current_replicas)
    redis.lpush('time_series', 0)


    thread = threading.Thread(target = flask_app)
    thread.start()

    while True:
        autoscaler.perform_scaling()
        time.sleep(5) # for the scaling to finish
