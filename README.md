WSGI middleware + flask blueprint for recording traces and viewing them in perfetto.

# To demo

Run:

```
poetry install
poetry shell
FLASK_DEBUG=1 flask --app tests.profapp run
```

Go to `http://localhost:5000/config` and click "enabled" and submit.

Go to `http://localhost:5000/profiles` and refresh this page a few times.
(It's recording a trace each time you view the page)

Pick a trace and click "view" and you should see it in the trace viewer. Use
"WASD" keys to zoom-in/out and scroll.


