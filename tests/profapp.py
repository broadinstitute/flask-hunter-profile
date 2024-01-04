from flask import Flask, render_template, request, redirect, url_for, make_response, send_from_directory
import json
import os
from flask_hunter_profile.middleware import ProfilingMiddleware
from flask_hunter_profile.service import Config
from flask_hunter_profile.flask_blueprint import flask_hunter_profile
from flask_wtf.csrf import CSRFProtect

COOKIE_NAME = 'hunter-profile'
log_dir = "logs"

app = Flask(__name__)
csrf = CSRFProtect()
csrf.init_app(app)

app.config["SECRET_KEY"] = "not really"

@app.route("/")
def hello_world():
    for i in range(10):
        inner(i)
    return "<p>Hello, World!</p>"

def inner(i):
    import time
    time.sleep(0.001)
    return str(i)

app.register_blueprint(flask_hunter_profile)

app.wsgi_app = ProfilingMiddleware(app.wsgi_app, Config(log_dir, COOKIE_NAME))
