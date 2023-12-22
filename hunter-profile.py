from hunter.actions import Action
from hunter.actions import RETURN_VALUE
import time
import json

import queue
from dataclasses import dataclass

@dataclass
class StartTrace:
    name: str
    log_path: str

@dataclass
class EndTrace:
    name: str

@dataclass
class AddTraceEvent:
    name: str
    payload: dict

@dataclass
class TraceLogState:
    name: str
    file: object
    is_first: bool

def trace_log_main_loop(trace_event_queue):
    # map of trace name -> file object per log
    open_logs = {}

    while True:
        try:
            event = trace_event_queue.get(block=True, timeout=1)
        except queue.Empty:
            # periodically flush out any buffered writes
            for file in open_logs.values():
                file.flush()
            continue

        if isinstance(event, StartTrace):
            file = open(event.log_path, "wt")
            assert event.name not in open_logs
            open_logs[event.name] = TraceLogState(event.name, file, True)
            file.write("[")
        elif isinstance(event, EndTrace):
            state = open_logs[event.name]
            file = state.file
            file.write("]\n")
            file.close()
            del open_logs[event.name]
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
    
import threading
import os

class ProfileAction(Action):
    def __init__(self, trace_name, trace_event_queue):
        self.timings = {}
        self.start = time.perf_counter()
        self.pid = os.getpid()
        self.tid = threading.get_ident()
        self.trace_event_queue = trace_event_queue
        self.trace_name = trace_name
 
    def __call__(self, event):
        current_time = time.perf_counter()
        frame_id = id(event.frame)

        if event.kind == 'call':
            self.timings[frame_id] = current_time, None
        elif frame_id in self.timings:
            if event.kind == 'exception' or event.kind == 'return':
                start_time, exception = self.timings.pop(frame_id)

                if event.kind == 'exception':
                    # store the exception
                    # (there will be a followup 'return' event in which we deal with it)
                    self.timings[frame_id] = start_time, event.arg
                elif event.kind == 'return':
                    delta = current_time - start_time

                    je = {
                        "name": f"{event.module} {event.function}",
                        "cat": "foo",
                        "ph": "X",
                        "ts": int((start_time-self.start) * 100000),
                        "dur": int(delta * 100000),
                        "pid": self.pid,
                        "tid": self.tid,
                        }

                    self.trace_event_queue.put(AddTraceEvent(name=self.trace_name,
                                                    payload=je))

                    # if event.instruction == RETURN_VALUE:
                    #     # exception was discarded
                    #     print(f'{event.function} returned.\n')
                    # else:
                    #     print(f'{event.function} raised exception: {exception}\n')

#{
#   "name": "myName",
#   "cat": "category,list",
#   "ph": "X",
#   "ts": 12345,
#   "pid": 123,
#   "tid": 456,
#   "args": {
#     "someArg": 1,
#     "anotherArg": {
#       "value": "my value"
#     }
#   }


trace_event_queue = queue.Queue()
trace_name = "sample"
log_path="sample_trace_log.json"

trace_log_writer = threading.Thread(target=trace_log_main_loop, args=[trace_event_queue], name="trace log writer", daemon=True)
trace_log_writer.start()

import hunter
import requests
with open("trace.json", "wt") as fd:
    trace_event_queue.put(StartTrace(name=trace_name,
                                    log_path=log_path))

    action = ProfileAction(trace_name, trace_event_queue)
    with hunter.trace(hunter.Q(module_sw="requests") & ( ~hunter.Q(kind="line")), action=action) as t:
        response = requests.get("https://news.ycombinator.com/")
        print(len(response.content))


    trace_event_queue.put(EndTrace(name=trace_name))
