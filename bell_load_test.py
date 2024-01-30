from locust import HttpUser,LoadTestShape,TaskSet,task, constant


class UserTasks(TaskSet):
    @task
    def get_root(self):
        self.client.get("/")

class User(HttpUser):
    wait_time = constant(1)
    tasks = {UserTasks}
    host = 'http://10.2.7.79:8000'

# https://github.com/locustio/locust/blob/master/examples/custom_shape/stages.py
class BellShape(LoadTestShape):
    time_limit = 600
    spawn_rate = 5
    stages = [
        {"duration": 60, "users": 10, "spawn_rate": 10}, # 0-1 min
        {"duration": 180, "users": 50, "spawn_rate": 10}, # 1-3 min
        {"duration": 300, "users": 100, "spawn_rate": 10}, # 3-5 min
        {"duration": 420, "users": 50, "spawn_rate": 10}, # 5-7 min
        {"duration": 480, "users": 10, "spawn_rate": 10} # 7-8 min
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                tick_data = (stage["users"], stage["spawn_rate"])
                return tick_data

        return None