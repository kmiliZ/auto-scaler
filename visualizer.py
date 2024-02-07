from flask import Flask, render_template,make_response
from redis import Redis

redis = Redis(host='10.2.7.79', port=6379,decode_responses=True)

app = Flask(__name__)

import plotly.express as px
import json
def write_html():
    # Generate some sample data (you'll replace this with your actual data)
    replicas_count = redis.lrange('replicas',0,-1)
    avg_response_time = redis.lrange('avg_response_time',0,-1)

    x_values = [1, 2, 3, 4, 5]

    # Create the scatter plot
    fig = px.bar(x=x_values, y=replicas_count, title="Number of Replicas Plot")

    # Save the plot as an HTML file
    fig.write_html("plot.html")
@app.route('/')
def index():
    # Read the saved HTML file (plot.html) and render it
    # with open("plot.html", "r") as f:
    #     plot_html = f.read()
    # return redis.get('hits')
    return render_template("index.html")

def flask_app():
    app.run(host='0.0.0.0', port=5001)

def write_html():
    # Generate some sample data (you'll replace this with your actual data)
    replicas_count = redis.lrange('size',0,-1)
    avg_response_time = redis.lrange('avg_response_t',0,-1)
    print("replicas_count =",replicas_count)

    # x_values = [1]

    # Create the scatter plot
    fig = px.bar(x=replicas_count, y=replicas_count, title="Number of Replicas Plot")
    fig2 = px.bar(x=avg_response_time, y=avg_response_time, title="Average Response Plot")

    # Save the plot as an HTML file
    fig.write_html("plot.html")
    fig2.write_html("plot2.html")