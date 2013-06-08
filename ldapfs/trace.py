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
        if trace_file == "-":
            handler = logging.StreamHandler()
        else:
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
        if 'self' in frame.f_locals:
            namespace = frame.f_locals['self'].__class__.__name__
        else:
            namespace = os.path.basename(path)

        # Get the function args from the stack frame
        (arg_names, varg_name, kw_name, f_locals) = inspect.getargvalues(frame)
        if name == '__init__' and 'self' in arg_names:
            # Don't try to format self. The object will not be constructed
            # yet. Print a repr instead.
            arg_names.remove('self')
            args = ['self={}'.format(repr(f_locals['self']))]
        else:
            args = []
        args.extend(['{}={}'.format(aname, f_locals[aname])
                    for aname in arg_names])
        if varg_name:
            args.append('{}={}'.format(varg_name, f_locals[varg_name]))
        if kw_name:
            args.append('{}={}'.format(kw_name, f_locals[kw_name]))

        if event == 'call':
            msg = '{}.{}:{}({})' \
                  .format(namespace, name, frame.f_lineno, ', '.join(args))
        elif event == 'return':
            msg = '{}.{}:{}({}) -> {}' \
                  .format(namespace, name, frame.f_lineno, ', '.join(args),
                          str(arg))
        LOG.debug(msg)
        return self


def start(trace_file, filter_dir):
    """Start tracing execution."""
    sys.settrace(Tracer(trace_file, filter_dir))


def stop():
    """Stop tracing execution."""
    sys.settrace(None)
