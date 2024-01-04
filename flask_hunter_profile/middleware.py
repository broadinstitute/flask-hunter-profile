import queue
import threading
from dataclasses import dataclass
import typing
import gzip
import json
import os
import http.cookies
import logging
import hunter
import re
import datetime
import time
from hunter.actions import Action
from hunter.actions import RETURN_VALUE
from .service import profiler_context, Config

log = logging.getLogger(__name__) ; test_value = "test"

class SettingsParseException(Exception):
    def __init__(self, cookie_value):
        super().__init__(self)
        self.cookie_value=cookie_value

@dataclass
class StartTrace:
    name: str
    log_path: str

@dataclass
class EndTrace:
    name: str
    description: str

@dataclass
class AddTraceEvent:
    name: str
    payload: dict

@dataclass
class TraceLogState:
    log_path: str
    name: str
    file: object
    is_first: bool

@dataclass
class TraceWatch:
    function: str
    parameters: typing.List[str]

@dataclass
class TraceSettings:
    name: str
    enabled: bool
    url_pattern: str
    watches : typing.List[TraceWatch]
#    modules: typing.List[str]


if typing.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment
else:
    class StartResponse:
        pass
    class WSGIApplication:
        pass
    class WSGIEnvironment: 
        pass

def trace_log_main_loop(trace_event_queue):
    # map of trace name -> file object per log
    open_logs = {}

    while True:
        try:
            event = trace_event_queue.get(block=True, timeout=1)
        except queue.Empty:
            # periodically flush out any buffered writes
            for file in open_logs.values():
                file.file.flush() 
            continue

        if isinstance(event, StartTrace):
            file = gzip.open(event.log_path, "wt")
            assert event.name not in open_logs
            open_logs[event.name] = TraceLogState(event.log_path, event.name, file, True)
            file.write("[")
        elif isinstance(event, EndTrace):
            state = open_logs[event.name]
            del open_logs[event.name]

            file = state.file
            file.write("]\n")
            file.close()
            
            metadata_filename = f"{state.log_path}.metadata"
            with open(metadata_filename, "wt") as fd:
                fd.write(json.dumps({"description": event.description}))


        elif isinstance(event, AddTraceEvent):
            state = open_logs[event.name]
            file = state.file
            if not state.is_first:
                file.write(",\n")
            else:
                state.is_first = False
            file.write(json.dumps(event.payload))
        else:
            raise AssertionError("Unknown event type")

class ProfilingMiddleware:
    def __init__(self,
        app: WSGIApplication,
        config: Config
        ):
        self.app = app
        self.trace_event_queue = queue.Queue()
        self.config = config
        self.trace_log_dir = config.trace_log_dir
        self.lock = threading.Lock()
        self.initialized = False
        self.next_trace_id = 1
        self.cookie_name = config.cookie_name

    def _initialize(self):
        self.lock.acquire()
        if not self.initialized:
            if not os.path.exists(self.trace_log_dir):
                os.makedirs(self.trace_log_dir)
            self.trace_log_writer = threading.Thread(target=trace_log_main_loop, args=[self.trace_event_queue], name="trace log writer", daemon=True)
            self.trace_log_writer.start()
            self.initialized = True
        self.lock.release()

    def _get_trace_id(self):
        self.lock.acquire()
        trace_id = self.next_trace_id
        self.next_trace_id+=1
        self.lock.release()
        return trace_id

    def _get_trace_settings(self, environ: WSGIEnvironment):
        cookie_str = environ.get('HTTP_COOKIE')
        if cookie_str is None:
            return None

        cookie = http.cookies.SimpleCookie()
        cookie.load(cookie_str)
        if self.cookie_name not in cookie:
            return None

        settings_json = cookie[self.cookie_name].value
        try:
            settings_dict = json.loads(settings_json)
            trace_settings = TraceSettings(**settings_dict)
        except Exception as ex:
            raise SettingsParseException(settings_json) from ex
        return trace_settings

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> typing.Iterable[bytes]:
        try:
            trace_settings = self._get_trace_settings(environ)
        except SettingsParseException as ex:
            log.exception("Could not parse trace settings cookie: %s", repr(ex.cookie_value))
            start_response(b"400 OK", [("Content-Type", "text/plain")])
            return [
                (f"Could not parse {self.cookie_name} cookie. Remove cookie in browser to eliminate this error").encode("utf8")
            ]        

        path_info = environ.get("PATH_INFO")
        method = environ.get("REQUEST_METHOD")
        if trace_settings is not None:
            # check to see if the request matches the url patterns being traced
            m = re.match(trace_settings.url_pattern, path_info)
            if m is None:
                # this url doesn't match, so clear trace_settings to pass through this request with no profiling
                trace_settings = None

        if trace_settings is None:
            # pass through with no tracing, but select this instance so we can get configurate information from it
            with profiler_context(self):
                return self.app(environ, start_response)
        else:
            # set up a new trace and start profiling
            self._initialize()
            log_path = os.path.join(self.trace_log_dir, f"{trace_settings.name}-{datetime.datetime.now().isoformat().replace('-', '').replace(':', '')}.json.gz")
            trace_id = self._get_trace_id()
            self.trace_event_queue.put(StartTrace(name=trace_id,
                                            log_path=log_path))


            action = ProfileAction(trace_id, self.trace_event_queue, trace_settings.watches)
            description=f"{method} {path_info}"
            action.emit_metadata(trace_id, description=description)
            start = time.perf_counter()
            try:
                with profiler_context(self):
                    condition = hunter.Q(stdlib=False) & ( hunter.Q(kind_in=["return", "call"]) )
                    with hunter.trace( condition, action=action) as t:
                        result = self.app(environ, start_response)
            finally:
                end = time.perf_counter()
                self.trace_event_queue.put(EndTrace(name=trace_id, description=f"{method} {path_info} {int((end-start)*1000)} msecs"))
            return result

class ProfileAction(Action):
    def __init__(self, trace_name, trace_event_queue, watches: typing.List[TraceWatch]):
        self.timings = {}
        self.start = time.perf_counter()
        self.pid = os.getpid()
        self.tid = threading.get_ident()
        self.trace_event_queue = trace_event_queue
        self.trace_name = trace_name

        self.watches_by_function = {}
        for watch in watches:
            self.watches_by_function[watch.function] = watch.parameters
 
    def emit_metadata(self, trace_id, description):
        je = {
            "name": "thread_name",
            "ph": "M",
            "pid": self.pid,
            "tid": self.tid,
            "args": {"name" :description}
            }

        self.trace_event_queue.put(AddTraceEvent(name=trace_id, 
                                                payload=je))

    def __call__(self, event):
        current_time = time.perf_counter()
        frame_id = id(event.frame)

        if event.kind == 'call':
            variables_to_add = {}
            event.frame.f_trace_lines = False

            # see about adding any of the parameters to the log
            # variables = self.watches_by_function.get(event.function)
            # if variables:
            #     for variable in variables:
            #         if variable in event.locals:
            #             value = repr(event.locals[variable])
            #             if len(value) > 512:
            #                 value = value[:512]+"..."
            #         else:
            #             value = "MISSING"
            #         variables_to_add[variable] = value

            self.timings[frame_id] = current_time, variables_to_add
        elif frame_id in self.timings:
            if event.kind == 'return':
                start_time, variables_to_add = self.timings.pop(frame_id)
                delta = current_time - start_time
                args = {"module": event.module, 
                        "lineno": event.lineno, 
                        "filename": event.filename}
                args.update(variables_to_add)
                je = {
                    "name": event.function,
                    "cat": "foo",
                    "ph": "X",
                    "ts": int((start_time-self.start) * 100000),
                    "dur": int(delta * 100000),
                    "pid": self.pid,
                    "tid": self.tid,
                    "args": args
                    }

                self.trace_event_queue.put(AddTraceEvent(name=self.trace_name,
                                                    payload=je))

