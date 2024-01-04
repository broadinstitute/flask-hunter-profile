import os
from flask import render_template, request, send_from_directory, Blueprint, current_app, make_response, redirect, url_for
import json 
from . import service

flask_hunter_profile = Blueprint('flask_hunter_profile', __name__,
                        template_folder='templates', url_prefix="profiler")

@flask_hunter_profile.route("/profiles")
def list_profiles():
    files = []
    files = service.list_traces()
    return render_template("profiles.html", files=files)

@flask_hunter_profile.route("/profile")
def download_profile():
    # return render_template("view_profile.html")
    filename = request.args["filename"]
    config = service.get_current_profiler_config()
    return send_from_directory(os.path.abspath(config.trace_log_dir), filename, as_attachment=True)

@flask_hunter_profile.route("/config", methods=["POST", "GET"])
def config():
    config = service.get_current_profiler_config()

    if request.method == "POST":
        trace_module_patterns = request.form["trace_module_patterns"].split("\n")
        trace_module_patterns = [x.strip() for x in trace_module_patterns]
        trace_module_patterns = [x for x in trace_module_patterns if len(trace_module_patterns) > 0]

        cookie_value = json.dumps({"enabled": "enabled" in request.form, 
                                   "name": request.form["name"], 
                                   "url_pattern": request.form["url_pattern"],
                                    #  "watches": [],
                                    "trace_module_patterns": trace_module_patterns
                                     })
        response = make_response(redirect(url_for("flask_hunter_profile.config")))
        response.set_cookie(config.cookie_name, cookie_value)
        return response        
    else:
        cookie_value = request.cookies.get(config.cookie_name)
        if cookie_value is None:
            cookie_dict = {"enabled": False, "name": "profile", "url_pattern": ".*"}
        else:
            cookie_dict = json.loads(cookie_value)
        return render_template("config.html", config=cookie_dict)
