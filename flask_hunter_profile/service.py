import os
from dataclasses import dataclass
import json

@dataclass
class Config: 
    trace_log_dir: str
    cookie_name: str

from contextvars import ContextVar
context_stack = ContextVar('context_stack')

import contextlib

def _push_context(obj):
    stack = context_stack.get(None)
    if stack is None:
        stack = []
        context_stack.set(stack)
    stack.append(obj)

def _pop_context():
    stack = context_stack.get(None)
    assert stack  is not None and len(stack ) > 0
    return stack.pop()

@contextlib.contextmanager
def profiler_context(middleware):
    _push_context(middleware)
    try:
        yield
    finally:
        popped = _pop_context()
        assert popped == middleware

def get_current_profiler_config():
    stack = context_stack.get()
    assert stack is not None and len(stack) > 0
    return stack[-1].config

@dataclass
class ProfileFile:
    filename: str
    description: str
    mtime: int

def _read_trace_description(filename):
    config = get_current_profiler_config()
    assert filename.startswith(config.trace_log_dir)
    metadata_filename = f"{filename}.metadata"

    if not os.path.exists(metadata_filename):
        # since the metadata is written after the trace ends, 
        # some of these won't have metadata yet. Return None for these
        return None
    
    with open(metadata_filename, "rt") as fd:
       metadata = json.load(fd)
    return metadata['description']

def list_traces():
    config = get_current_profiler_config()
    log_dir = config.trace_log_dir
    files = []

    for filename in os.listdir(log_dir):
        if filename.endswith(".json.gz"):
            path = os.path.join(log_dir, filename)
            if not os.path.isfile(path):
                continue
            description = _read_trace_description(path)
            if description is None:
                continue
            files.append(ProfileFile(filename, description, os.path.getmtime(path)))

    return sorted(files, key=lambda x: x.mtime, reverse=True)

