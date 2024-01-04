import hunter
from flask_hunter_profile.middleware import ProfileAction
from queue import Queue
import time


def benchmark1():
    a = 0
    for i in range(1000):
        a += i
        a += i
        a += i
        a += i


def add(a, b):
    return a + b


def benchmark2():
    a = 0
    for i in range(1000):
        a = add(a, i)
        a = add(a, i)
        a = add(a, i)
        a = add(a, i)


def benchmark3():
    a = 0
    i = 0
    while i < 1000:
        a += 1
        a += 1
        a += 1
        a += 1
        i += 1


def sample_generator(max_value):
    i = 0
    while i < 1000:
        yield i
        i += 1


def benchmark4():
    a = 0
    for i in sample_generator(1000):
        a += i
        a += i
        a += i
        a += i


import seaborn as sns
import matplotlib.pyplot as plt


def benchmark5():
    # create a seaborn plot
    sns.set(style="darkgrid")
    tips = sns.load_dataset("tips")
    ax = sns.scatterplot(x="total_bill", y="tip", data=tips)

    # save the plot as PNG file
    plt.savefig("seaborn_plot.png")


import sys

import contextlib
from dataclasses import dataclass


@dataclass
class Event:
    kind: str
    frame: object
    module: str
    function: str
    lineno: int
    filename: str


@contextlib.contextmanager
def trivial_trace(action):
    def trace_handler(frame, event, arg):
        if event == "call":
            # disable per line tracing
            frame.f_trace_lines = False

            action(Event(event, frame, "x", "y", 1, "z"))

            return trace_handler
        elif event == "return":
            action(Event(event, frame, "x", "y", 1, "z"))

            return trace_handler
        return trace_handler

    sys.settrace(trace_handler)
    yield
    sys.settrace(None)


def hunter_profiler(action):
    condition = hunter.Q(stdlib=False) & (hunter.Q(kind_in=["return", "call"]))
    return hunter.trace(condition, action=action)


@contextlib.contextmanager
def tiny_profiler(action):
    from flask_hunter_profile.tiny_tracer import Handler, Tracer

    handler = Handler(
        stop_tracing_module_patterns=[], skip_action_modules=[], action=action
    )
    tracer = Tracer()
    m = tracer.trace(handler)

    #    m = trace(stop_tracing_module_patterns=[], skip_action_modules=[], action=action)
    with m:
        yield
    print("modules", handler.seen_modules)


@contextlib.contextmanager
def tiny_profiler_2(action):
    from flask_hunter_profile.tiny_tracer import Handler, Tracer

    handler = Handler(trace_module_patterns=["tests\\.benchmark"], action=action)
    tracer = Tracer()
    m = tracer.trace(handler)

    #    m = trace(stop_tracing_module_patterns=[], skip_action_modules=[], action=action)
    with m:
        yield
    print("modules", handler.seen_modules)
    print("trace_option_by_module", handler.trace_option_by_module.keys())


def main():
    run_benchmark(benchmark5, iterations=1)
    run_benchmark(benchmark5, tracer_ctx_mgr=tiny_profiler_2, iterations=1)


def foo(e):
    return None


def run_benchmark(generate_load, iterations=100, tracer_ctx_mgr=hunter_profiler):
    trace_id = 1
    trace_event_queue = Queue()

    action = ProfileAction(trace_id, trace_event_queue, [])
    #    action = foo # lambda x: None

    # warmup
    generate_load()

    start = time.perf_counter_ns()
    for i in range(iterations):
        generate_load()
    end = time.perf_counter_ns()
    load_duration = end - start

    start = time.perf_counter_ns()
    with tracer_ctx_mgr(action) as t:
        for _ in range(iterations):
            generate_load()
    end = time.perf_counter_ns()

    profiled_load_duration = end - start

    profile_overhead_per_iteration = (
        profiled_load_duration - load_duration
    ) / iterations
    event_count = 0
    while not trace_event_queue.empty():
        trace_event_queue.get()
        event_count += 1
    print(
        generate_load,
        f"overhead: {profile_overhead_per_iteration/1000000} ms, {event_count}",
    )


if __name__ == "__main__":
    main()
