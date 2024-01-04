import hunter
from hunter import Event
import traceback

class ContinueTraceOption:
    def __init__(self, name):
        self.name = name
    def __repr__(self) -> str:
        return self.name

TRACE_CHILD = ContinueTraceOption("TRACE_CHILD")
NO_TRACE = ContinueTraceOption("NO_TRACE")

from typing import Callable
import sys
import threading
import traceback
class Tracer(hunter.Tracer):

    # def trace(self, predicate):
    #     """
    #     Starts tracing with the given callable.

    #     Args:
    #         predicate (callable that accepts a single :obj:`~hunter.event.Event` argument):
    #     Return:
    #         self
    #     """
    #     self._handler = predicate
    #     if self.profiling_mode:
    #         if self.threading_support is None or self.threading_support:
    #             self._threading_previous = getattr(threading, '_profile_hook', None)
    #             threading.setprofile(self)
    #         self._previous = sys.getprofile()
    #         sys.setprofile(self)
    #     else:
    #         if self.threading_support is None or self.threading_support:
    #             self._threading_previous = getattr(threading, '_trace_hook', None)
    #             threading.settrace(self)
    #         self._previous = sys.gettrace()
    #         sys.settrace(self)
    #     return self


    def __call__(self, frame, kind, arg):
        # don't both tracing individual lines
        frame.f_trace_lines = False

        if self._handler is not None:
            event = Event(frame, kind, arg, self)
            try:
                option = self._handler(event)
            except Exception as exc:
                traceback.print_exc(file=hunter._default_stream)
                hunter._default_stream.write(f'Disabling tracer because handler {self._handler!r} failed ({exc!r}) at {event!r}.\n\n')
                self.stop()
                return None

            if option is TRACE_CHILD:
                return self
            else:
                return None


from hunter.const import SITE_PACKAGES_PATHS, SYS_PREFIX_PATHS

# def is_stdlib(module, filename):
#     module_parts = module.split('.')
#     if 'pkg_resources' in module_parts:
#         # skip this over-vendored module
#         return True
#     elif (module.startswith('namedtuple_') or module == 'site'):
#         # skip namedtuple exec garbage
#         return True
#     elif filename.startswith(SITE_PACKAGES_PATHS):
#         # if it's in site-packages then its definitely not stdlib
#         return False
#     elif filename.startswith(SYS_PREFIX_PATHS):
#         return True
#     else:
#         return False

import re

class Handler():
    def __init__(self, trace_module_patterns=[], skip_action_modules=[], action=lambda event: None):
        self.trace_option_by_module = {}
        self.skip_action_modules = set(skip_action_modules)
        self.trace_module_patterns=[re.compile(x) for x in trace_module_patterns]
        self.action = action
        self.seen_modules = set()

    def __call__(self, event: hunter.Event): 
        # print("handler.__call__", event.kind, event.function, event.module)
        # module = event.frame.f_globals.get('__name__', '?')

        # check the caller's module to decide whether we want to trace into function
        module = event.frame.f_back.f_globals.get('__name__', '?')

        self.seen_modules.add(module)

        # check cache by module
        trace_option = self.trace_option_by_module.get(module)

        # if not in cache, determine whether we trace into this module by regex name match
        if trace_option is None:
            trace_option = NO_TRACE

            # a bit of a hack: Ensure that we always trace at least the top level 
            # because otherwise we can't see what the child modules are we might want
            # to add in the future. Do this by adding the module of the first time we get called.
            if len(self.trace_option_by_module) == 0:
                trace_option = TRACE_CHILD
            else:
                for trace_module_pattern in self.trace_module_patterns:
                    if trace_module_pattern.match(module):
                        trace_option = TRACE_CHILD
                        break

            # store conclusion into cache
            self.trace_option_by_module[module] = trace_option

        if trace_option is TRACE_CHILD and module not in self.skip_action_modules:
            self.action(event)

        # print("returning", trace_option)
        return trace_option

def trace(**options):
    handler: Callable[[hunter.Event], ContinueTraceOption] = Handler(**options)
    tracer = Tracer()
    return tracer.trace(handler)
