#!/usr/bin/env python

import sys
import logging
from functools import partial


LOG = logging.getLogger(__name__)


def trace_calls(filter_dir, frame, event, arg):
    if event not in ('call', 'return'):
        return partial(trace_calls, filter_dir)

    co = frame.f_code
    dst_name = co.co_name
    if dst_name == 'write':
        # Ignore write() calls from print statements
        return partial(trace_calls, filter_dir)

    dst_lineno = frame.f_lineno
    dst_filename = co.co_filename

    if filter_dir and not dst_filename.startswith(filter_dir):
        return partial(trace_calls, filter_dir)

    src_name, src_filename, src_lineno = '?', '?', '?'
    src = frame.f_back
    if src:
        if src.f_code:
            src_name = src.f_code.co_name
        src_lineno = src.f_lineno
        src_filename = src.f_code.co_filename

    if event == 'call':
        msg = '{} ({}:{}) -> {} ({}:{})'.format(
              src_name, src_filename, src_lineno,
              dst_name, dst_filename, dst_lineno)
    elif event == 'return':
        msg = '{} returned by {} ({}:{}) -> {} ({}:{})'.format(arg,
              dst_name, dst_filename, dst_lineno,
              src_name, src_filename, src_lineno)
    LOG.debug(msg)
    return partial(trace_calls, filter_dir)


def start(filter_dir=None):
    sys.settrace(partial(trace_calls, filter_dir))


def stop():
    sys.settrace(None)
