"""
Functions for working with the terminal.
"""
from __future__ import print_function

import os
import sys

import curses

import fcntl
import termios
import struct


def _unicode(s, encoding='utf-8'):
        if type(s) == bytes:
            return s.decode(encoding, 'ignore')
        else:
            return str(s)


def terminal_get_size(default_size=(25, 80)):
    """
    Return (number of rows, number of columns) for the terminal,
    if they can be determined, or `default_size` if they can't.
    """

    def ioctl_gwinsz(fd):  # TABULATION FUNCTIONS
        try:  # Discover terminal width
            return struct.unpack(
                'hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234')
            )
        except Exception:
            return None

    # try open fds
    size = ioctl_gwinsz(0) or ioctl_gwinsz(1) or ioctl_gwinsz(2)
    if not size:
        # ...then ctty
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            size = ioctl_gwinsz(fd)
            os.close(fd)
        except Exception:
            pass
    if not size:
        # env vars or finally defaults
        try:
            size = (os.environ['LINES'], os.environ['COLUMNS'])
        except Exception:
            return default_size

    return map(int, size)


def terminal_clear():
    """
    Like calling the `clear` UNIX command.  If that fails, just prints a bunch
    of newlines :-P
    """
    if not _terminal_use_capability('clear'):
        print('\n' * 8)


def terminal_move_to_beginning_of_line():
    """
    Jumps the cursor back to the beginning of the current line of text.
    """
    if not _terminal_use_capability('cr'):
        print()


def _terminal_use_capability(capability_name):
    """
    If the terminal supports the given capability, output it.  Return whether
    it was output.
    """
    curses.setupterm()
    capability = curses.tigetstr(capability_name)
    if capability:
        sys.stdout.write(_unicode(capability))
    return bool(capability)


def terminal_print(text, color):
    """Print text in the specified color, without a terminating newline."""
    _terminal_set_color(color)
    print(text, end='')
    _terminal_restore_color()


def _terminal_set_color(color):
    def color_code(set_capability, possible_colors):
        try:
            color_index = possible_colors.split(' ').index(color)
        except ValueError:
            return None
        set_code = curses.tigetstr(set_capability)
        if not set_code:
            return None
        return curses.tparm(set_code, color_index)
    code = (
        color_code(
            'setaf', 'BLACK RED GREEN YELLOW BLUE MAGENTA CYAN WHITE'
        ) or color_code(
            'setf', 'BLACK BLUE GREEN CYAN RED MAGENTA YELLOW WHITE'
        )
    )
    if code:
        code = _unicode(code)
        sys.stdout.write(code)


def _terminal_restore_color():
    restore_code = curses.tigetstr('sgr0')
    if restore_code:
        sys.stdout.write(_unicode(restore_code))
