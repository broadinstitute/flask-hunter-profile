from flask_hunter_profile.tiny_tracer import trace
from collections import defaultdict

from .sample_functions import call_c, call_a, call_b

def test_basic_trace():
    event_counts = defaultdict(lambda : 0)

    def log_function(event):
        event_counts[f"{event.kind} {event.function}"] += 1

    with trace(action=log_function, trace_module_patterns=["tests\\..*"]):
        call_b(100)

    assert event_counts["call call_a"] == 2
    assert event_counts["call call_b"] == 1
    assert event_counts["return call_a"] == 2
    assert event_counts["return call_b"] == 1


def test_execution_trace():
    event_counts = defaultdict(lambda : 0)

    def log_function(event):
        event_counts[f"{event.kind} {event.function}"] += 1

    def throws_ex():
        raise KeyError("x")

    def parent_call():
        throws_ex()

    def top_fn():
        try:
            parent_call()
        except KeyError:
            pass

    with trace(action=log_function, trace_module_patterns=["tests\\.test_.*"]):
        top_fn()

    assert event_counts["call top_fn"] == 1
    assert event_counts["return top_fn"] == 1
    assert event_counts["call parent_call"] == 1
    assert event_counts["return parent_call"] == 1
    assert event_counts["call throws_ex"] == 1
    assert event_counts["return throws_ex"] == 1

def test_filtered_trace():
    event_counts = defaultdict(lambda : 0)

    def log_function(event):
        event_counts[f"{event.kind} {event.function}"] += 1

    def top_fn():
        call_c(100)

    with trace(action=log_function, trace_module_patterns=["tests\\.test_.*"]):
        top_fn()


    assert event_counts["call top_fn"] == 1
    assert event_counts["return top_fn"] == 1

    assert event_counts["call call_c"] == 1
    assert event_counts["return call_c"] == 1

    assert event_counts["call call_a"] == 0
    assert event_counts["return call_a"] == 0

    assert event_counts["call call_b"] == 0
    assert event_counts["return call_b"] == 0
