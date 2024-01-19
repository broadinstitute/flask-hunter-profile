import hunter
import hunter.tracer
from hunter.event import Event
import traceback
import re
from typing import Callable
import traceback


class ContinueTraceOption:
    def __init__(self, name):
        self.name = name

    def __repr__(self) -> str:
        return self.name


TRACE_CHILD = ContinueTraceOption("TRACE_CHILD")
NO_TRACE = ContinueTraceOption("NO_TRACE")


class Tracer(hunter.tracer.Tracer):
    # need to override the __call__ method on tracer in order to change behavior of handler.
    # at this point, would it make more sense to copy the whole class and fork the implementation?

    def __call__(self, frame, kind, arg):
        # don't both tracing individual lines
        frame.f_trace_lines = False

        if self._handler is not None:
            event = Event(frame, kind, arg, self)
            try:
                option = self._handler(event)
            except Exception as exc:
                traceback.print_exc(file=hunter._default_stream)
                hunter._default_stream.write(
                    f"Disabling tracer because handler {self._handler!r} failed ({exc!r}) at {event!r}.\n\n"
                )
                self.stop()
                return None

            if option is TRACE_CHILD:
                return self
            else:
                return None


class Handler:
    def __init__(
        self,
        trace_module_patterns=[],
        skip_action_modules=[],
        action=lambda event: None,
    ):
        self.trace_option_by_module = {}
        self.skip_action_modules = set(skip_action_modules)
        self.trace_module_patterns = [
            re.compile(f"^{x}$") for x in trace_module_patterns
        ]
        self.action = action
        self.seen_modules = set()

    def __call__(self, event: hunter.Event):
        # check the caller's module to decide whether we want to trace into function
        f_back = event.frame.f_back
        if f_back:
            module = f_back.f_globals.get("__name__", "?")
        else:
            module = "?"

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
                # print("Adding first module", module)
                trace_option = TRACE_CHILD
            else:
                for trace_module_pattern in self.trace_module_patterns:
                    if trace_module_pattern.match(module):
                        trace_option = TRACE_CHILD
                        # print("caller module passed check", module, trace_module_pattern)
                        break
                # if trace_option == NO_TRACE:
                #    print("caller module did not pass check", module, self.trace_module_patterns)

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
