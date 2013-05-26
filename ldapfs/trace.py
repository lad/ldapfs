#!/usr/bin/env python

"""Function tracing using sys.settrace."""

import os
import sys
import logging
import inspect


LOG = logging.getLogger(__name__)


class Tracer(object):
    """Trace functions with args and return values.
    
       Setup with: sys.settrace(Tracer(trace_file, filter_dir))
    """

    def __init__(self, trace_file, filter_dir):
        self.filter_dir = filter_dir
        if os.path.isfile(trace_file):
            os.remove(trace_file)
        handler = logging.FileHandler(trace_file)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter('%(message)s'))
        LOG.addHandler(handler)

    def __call__(self, frame, event, arg):
        """Trace callback used wtih sys.settrace."""
        if event not in ('call', 'return'):
            return self

        # Return if the called or calling file path doesn't match the filter
        path = frame.f_code.co_filename
        if self.filter_dir and not path.startswith(self.filter_dir) and \
           (not frame.f_back or
            not frame.f_back.f_code.co_filename.startswith(self.filter_dir)):
            return self

        name = frame.f_code.co_name
        lineno = frame.f_lineno
        filename = os.path.basename(path)
        if 'self' in frame.f_locals:
            cls = frame.f_locals['self'].__class__.__name__
        else:
            cls = ''

        # Get the function args from the stack frame
        (args, varargs, kwargs, local) = inspect.getargvalues(frame)
        args = ['{}={}'.format(aname, local[aname]) for aname in args]
        if varargs:
            args.append('{}={}'.format(varargs, local[varargs]))
        if kwargs:
            args.append('{}={}'.format(kwargs, local[kwargs]))

        if event == 'call':
            msg = '{}.{}:{}({})' \
                  .format(cls or filename, name, lineno, ', '.join(args))
        elif event == 'return':
            msg = '{}.{}:{}({}) -> {}' \
                  .format(cls or filename, name, lineno, ', '.join(args),
                          str(arg))
        LOG.debug(msg)
        return self


def start(trace_file, filter_dir):
    """Start tracing execution."""
    sys.settrace(Tracer(trace_file, filter_dir))


def stop():
    """Stop tracing execution."""
    sys.settrace(None)
