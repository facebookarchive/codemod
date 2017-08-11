#!/usr/bin/env python

# Copyright (c) 2007-2008 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# See accompanying file LICENSE.
#
# @author Justin Rosenstein

from __future__ import print_function

import argparse
import fnmatch
import os
import re
import sys
import textwrap
from math import ceil

if sys.version_info[0] >= 3:
    unicode = str


def is_extensionless(path):
    """
    Returns True if path has no extension.

    >>> is_extensionless("./www/test")
    True
    >>> is_extensionless("./www/.profile")
    True
    >>> is_extensionless("./www/.dir/README")
    True
    >>> is_extensionless("./scripts/menu.js")
    False
    >>> is_extensionless("./LICENSE")
    True
    """
    _, ext = os.path.splitext(path)
    return ext == ''


def matches_extension(path, extension):
    """
    Returns True if path has the given extension, or if
    the last path component matches the extension. Supports
    Unix glob matching.

    >>> matches_extension("./www/profile.php", "php")
    True
    >>> matches_extension("./scripts/menu.js", "html")
    False
    >>> matches_extension("./LICENSE", "LICENSE")
    True
    """
    _, ext = os.path.splitext(path)
    if ext == '':
        # If there is no extension, grab the file name and
        # compare it to the given extension.
        return os.path.basename(path) == extension
    else:
        # If the is an extension, drop the leading period and
        # compare it to the extension.
        return fnmatch.fnmatch(ext[1:], extension)


def path_filter(extensions, exclude_paths=None):
    """
    Returns a function that returns True if a filepath is acceptable.

    @param extensions     An array of strings. Specifies what file
                          extensions should be accepted by the
                          filter. If None, we default to the Unix glob
                          `*` and match every file extension.
    @param exclude_paths  An array of strings which represents filepaths
                          that should never be accepted by the filter. Unix
                          shell-style wildcards are supported.

    @return function      A filter function that will only return True
                          when a filepath is acceptable under the above
                          conditions.

    >>> list(map(path_filter(extensions=['js', 'php']),
    ...     ['./profile.php', './q.jjs']))
    [True, False]
    >>> list(map(path_filter(extensions=['*'],
    ...                 exclude_paths=['html']),
    ...     ['./html/x.php', './lib/y.js']))
    [False, True]
    >>> list(map(path_filter(extensions=['js', 'BUILD']),
    ...     ['./a.js', './BUILD', './profile.php']))
    [True, True, False]
    >>> list(map(path_filter(extensions=['js'],
    ...     exclude_paths=['*/node_modules/*']),
    ...     ['./a.js', './tools/node_modules/dep.js']))
    [True, False]
    """
    exclude_paths = exclude_paths or []

    def the_filter(path):
        if not any(matches_extension(path, extension)
                   for extension in extensions):
            return False
        if exclude_paths:
            for excluded in exclude_paths:
                if (path.startswith(excluded) or
                        path.startswith('./' + excluded) or
                        fnmatch.fnmatch(path, excluded)):
                    return False
        return True
    return the_filter


_default_path_filter = path_filter(
    extensions=['php', 'phpt', 'js', 'css', 'rb', 'erb']
)


def run_interactive(query, editor=None, just_count=False, default_no=False):
    """
    Asks the user about each patch suggested by the result of the query.

    @param query        An instance of the Query class.
    @param editor       Name of editor to use for manual intervention, e.g.
                        'vim'
                        or 'emacs'.  If omitted/None, defaults to $EDITOR
                        environment variable.
    @param just_count   If true: don't run normally.  Just print out number of
                        places in the codebase where the query matches.
    """

    global yes_to_all  # noqa

    # Load start from bookmark, if appropriate.
    bookmark = _load_bookmark()
    if bookmark:
        print('Resume where you left off, at %s (y/n)? '
              % str(bookmark), end=' ')
        sys.stdout.flush()
        if (_prompt(default='y') == 'y'):
            query.start_position = bookmark

    # Okay, enough of this foolishness of computing start and end.
    # Let's ask the user about some one line diffs!
    print('Searching for first instance...')
    suggestions = query.generate_patches()

    if just_count:
        for count, _ in enumerate(suggestions):
            terminal_move_to_beginning_of_line()
            print(count, end=" ")
            sys.stdout.flush()  # since print statement ends in comma
        print()
        return

    for patch in suggestions:
        _save_bookmark(patch.start_position)
        _ask_about_patch(patch, editor, default_no)
        print('Searching...')
    _delete_bookmark()
    if yes_to_all:
        terminal_clear()
        print(
            "You MUST indicate in your code review:"
            " \"codemod with 'Yes to all'\"."
            "Make sure you and other people review the changes.\n\n"
            "With great power, comes great responsibility."
        )


def line_transformation_suggestor(line_transformation, line_filter=None):
    """
    Returns a suggestor (a function that takes a list of lines and yields
    patches) where suggestions are the result of line-by-line transformations.

    @param line_transformation  Function that, given a line, returns another
                                line
                                with which to replace the given one.  If the
                                output line is different from the input line,
                                the
                                user will be prompted about whether to make the
                                change.  If the output is None, this means "I
                                don't have a suggestion, but the user should
                                still be asked if zhe wants to edit the line."
    @param line_filter          Given a line, returns True or False.  If False,
                                a line is ignored (as if line_transformation
                                returned the line itself for that line).
    """
    def suggestor(lines):
        for line_number, line in enumerate(lines):
            if line_filter and not line_filter(line):
                continue
            candidate = line_transformation(line)
            if candidate is None:
                yield Patch(line_number)
            else:
                yield Patch(line_number, new_lines=[candidate])
    return suggestor


def regex_suggestor(regex, substitution=None, ignore_case=False,
                    line_filter=None):
    if isinstance(regex, str):
        if ignore_case is False:
            regex = re.compile(regex)
        else:
            regex = re.compile(regex, re.IGNORECASE)

    if substitution is None:
        def line_transformation(line):
            return None if regex.search(line) else line
    else:
        def line_transformation(line):
            return regex.sub(substitution, line)
    return line_transformation_suggestor(line_transformation, line_filter)


def multiline_regex_suggestor(regex, substitution=None, ignore_case=False):
    """
    Return a suggestor function which, given a list of lines, generates patches
    to substitute matches of the given regex with (if provided) the given
    substitution.

    @param regex         Either a regex object or a string describing a regex.
    @param substitution  Either None (meaning that we should flag the matches
                         without suggesting an alternative), or a string (using
                         \1 notation to backreference match groups) or a
                         function (that takes a match object as input).
    """
    if isinstance(regex, str):
        if ignore_case is False:
            regex = re.compile(regex, re.DOTALL)
        else:
            regex = re.compile(regex, re.DOTALL | re.IGNORECASE)

    if isinstance(substitution, str):
        def substitution_func(match):
            return match.expand(substitution)
    else:
        substitution_func = substitution

    def suggestor(lines):
        pos = 0
        while True:
            match = regex.search(''.join(lines), pos)
            if not match:
                break
            start_row, start_col = _index_to_row_col(lines, match.start())
            end_row, end_col = _index_to_row_col(lines, match.end() - 1)

            if substitution is None:
                new_lines = None
            else:
                # TODO: ugh, this is hacky.  Clearly I need to rewrite
                # this to use
                # character-level patches, rather than line-level patches.
                new_lines = substitution_func(match)
                if new_lines is not None:
                    new_lines = ''.join((
                        lines[start_row][:start_col],
                        new_lines,
                        lines[end_row][end_col + 1:]
                    ))

            yield Patch(
                start_line_number=start_row,
                end_line_number=end_row + 1,
                new_lines=new_lines
            )
            pos = match.start() + 1

    return suggestor


def _index_to_row_col(lines, index):
    r"""
    >>> lines = ['hello\n', 'world\n']
    >>> _index_to_row_col(lines, 0)
    (0, 0)
    >>> _index_to_row_col(lines, 7)
    (1, 1)
    """
    if index < 0:
        raise IndexError('negative index')
    current_index = 0
    for line_number, line in enumerate(lines):
        line_length = len(line)
        if current_index + line_length > index:
            return line_number, index - current_index
        current_index += line_length
    raise IndexError('index %d out of range' % index)


class Query(object):
    """
    Represents a suggestor, along with a set of constraints on which files
    should be fed to that suggestor.

    >>> Query(lambda x: None, start='profile.php:20').start_position
    Position('profile.php', 20)
    """

    def __init__(self,
                 suggestor,
                 start=None,
                 end=None,
                 root_directory='.',
                 path_filter=_default_path_filter,
                 inc_extensionless=False):
        """
        @param suggestor            A function that takes a list of lines and
                                    generates instances of Patch to suggest.
                                    (Patches should not specify paths.)
        @param start                One of:
                                    - an instance of Position
                                    (indicating the place in the file
                                     hierarchy at which to resume),
                                    - a path:line_number-formatted string
                                      representing a position,
                                    - a string formatted like "25%"
                                    (indicating we should start 25% of
                                     the way through the process), or
                                    - None (indicating that we should
                                            start at the beginning).
        @param end                  An indicator of the position
                                    just *before* which
                                    to stop exploring, using one
                                    of the same formats
                                    used for start (where None  means
                                    'traverse to the end of the hierarchy).
        @param root_directory       The path whose ancestor files
                                    are to be explored.
        @param path_filter          Given a path, returns True or False.
                                    If False,
                                    the entire file is ignored.
        @param inc_extensionless    If True, will include all files without an
                                    extension when checking
                                    against the path_filter
        """
        self.suggestor = suggestor
        self._start = start
        self._end = end
        self.root_directory = root_directory
        self.path_filter = path_filter
        self.inc_extensionless = inc_extensionless
        self._all_patches_cache = None

    def clone(self):
        import copy
        return copy.copy(self)

    def _get_position(self, attr_name):
        attr_value = getattr(self, attr_name)
        if attr_value is None:
            return None
        if isinstance(attr_value, str) and attr_value.endswith('%'):
            attr_value = self.compute_percentile(int(attr_value[:-1]))
            setattr(self, attr_name, attr_value)
        return Position(attr_value)

    def get_start_position(self):
        return self._get_position('_start')
    start_position = property(get_start_position)

    @start_position.setter
    def start_position(self, value):
        self._start = value

    def get_end_position(self):
        return self._get_position('_end')
    end_position = property(get_end_position)

    @end_position.setter
    def end_position(self, value):
        self._end = value

    def get_all_patches(self, dont_use_cache=False):
        """
        Computes a list of all patches matching this query, though ignoreing
        self.start_position and self.end_position.

        @param dont_use_cache   If False, and get_all_patches has been called
                                before, compute the list computed last time.
        """
        if not dont_use_cache and self._all_patches_cache is not None:
            return self._all_patches_cache

        print(
            'Computing full change list (since you specified a percentage)...'
        ),
        sys.stdout.flush()  # since print statement ends in comma

        endless_query = self.clone()
        endless_query.start_position = endless_query.end_position = None
        self._all_patches_cache = list(endless_query.generate_patches())
        return self._all_patches_cache

    def compute_percentile(self, percentage):
        """
        Returns a Position object that represents percentage%-far-of-the-way
        through the larger task, as specified by this query.

        @param percentage    a number between 0 and 100.
        """
        all_patches = self.get_all_patches()
        return all_patches[
            int(len(all_patches) * percentage / 100)
        ].start_position

    def generate_patches(self):
        """
        Generates a list of patches for each file underneath
        self.root_directory
        that satisfy the given conditions given
        query conditions, where patches for
        each file are suggested by self.suggestor.
        """
        start_pos = self.start_position or Position(None, None)
        end_pos = self.end_position or Position(None, None)

        path_list = Query._walk_directory(self.root_directory)
        path_list = Query._sublist(path_list, start_pos.path, end_pos.path)
        path_list = (
            path for path in path_list if
            Query._path_looks_like_code(path) and
            (self.path_filter(path)) or
            (self.inc_extensionless and is_extensionless(path))
        )
        for path in path_list:
            try:
                lines = list(open(path))
            except IOError:
                # If we can't open the file--perhaps it's a symlink whose
                # destination no loner exists--then short-circuit.
                continue

            for patch in self.suggestor(lines):
                if path == start_pos.path:
                    if patch.start_line_number < start_pos.line_number:
                        continue  # suggestion is pre-start_pos
                if path == end_pos.path:
                    if patch.end_line_number >= end_pos.line_number:
                        break  # suggestion is post-end_pos

                old_lines = lines[
                    patch.start_line_number:patch.end_line_number]
                if patch.new_lines is None or patch.new_lines != old_lines:
                    patch.path = path
                    yield patch
                    # re-open file, in case contents changed
                    lines[:] = list(open(path))

    def run_interactive(self, **kargs):
        run_interactive(self, **kargs)

    @staticmethod
    def _walk_directory(root_directory):
        """
        Generates the paths of all files that are ancestors
        of `root_directory`.
        """

        paths = [os.path.join(root, name)
                 for root, dirs, files in os.walk(root_directory)  # noqa
                 for name in files]
        paths.sort()
        return paths

    @staticmethod
    def _sublist(items, starting_value, ending_value=None):
        """
        >>> list(Query._sublist((x*x for x in range(1, 100)), 16, 64))
        [16, 25, 36, 49, 64]
        """
        have_started = starting_value is None

        for x in items:
            have_started = have_started or x == starting_value
            if have_started:
                yield x

            if ending_value is not None and x == ending_value:
                break

    @staticmethod
    def _path_looks_like_code(path):
        """
        >>> Query._path_looks_like_code('/home/jrosenstein/www/profile.php')
        True
        >>> Query._path_looks_like_code('./tags')
        False
        >>> Query._path_looks_like_code('/home/jrosenstein/www/profile.php~')
        False
        >>> Query._path_looks_like_code('/home/jrosenstein/www/.git/HEAD')
        False
        """
        return (
            '/.' not in path and
            path[-1] != '~' and
            not path.endswith('tags') and
            not path.endswith('TAGS')
        )


class Position(object):
    """
    >>> p1, p2 = Position('./hi.php', 20), Position('./hi.php:20')
    >>> p1.path == p2.path and p1.line_number == p2.line_number
    True
    >>> p1
    Position('./hi.php', 20)
    >>> print(p1)
    ./hi.php:20
    >>> Position(p1)
    Position('./hi.php', 20)
    """

    def __init__(self, *path_and_line_number):
        """
        You can use the two parameter version, and pass a
        path and line number, or
        you can use the one parameter version, and
        pass a $path:$line_number string,
        or another instance of Position to copy.
        """
        if len(path_and_line_number) == 2:
            self.path, self.line_number = path_and_line_number
        elif len(path_and_line_number) == 1:
            arg = path_and_line_number[0]
            if isinstance(arg, Position):
                self.path, self.line_number = arg.path, arg.line_number
            else:
                try:
                    self.path, line_number_s = arg.split(':')
                    self.line_number = int(line_number_s)
                except ValueError:
                    raise ValueError(
                        'inappropriately formatted Position string: %s'
                        % path_and_line_number[0]
                    )
        else:
            raise TypeError('Position takes 1 or 2 arguments')

    def __repr__(self):
        return 'Position(%s, %d)' % (repr(self.path), self.line_number)

    def __str__(self):
        return '%s:%d' % (self.path, self.line_number)


class Patch(object):
    """
    Represents a range of a file and (optionally) a list of lines with which to
    replace that range.

    >>> p = Patch(2, 4, ['X', 'Y', 'Z'], 'x.php')
    >>> print(p.render_range())
    x.php:2-3
    >>> p.start_position
    Position('x.php', 2)
    >>> l = ['a', 'b', 'c', 'd', 'e', 'f']
    >>> p.apply_to(l)
    >>> l
    ['a', 'b', 'X', 'Y', 'Z', 'e', 'f']
    """

    def __init__(self, start_line_number, end_line_number=None, new_lines=None,
                 path=None):  # noqa
        """
        Constructs a Patch object.

        @param end_line_number  The line number just *after* the end of
                                the range.
                                Defaults to
                                start_line_number + 1, i.e. a one-line
                                diff.
        @param new_lines        The set of lines with which to
                                replace the range
                                specified, or a newline-delimited string.
                                Omitting this means that
                                this "patch" doesn't actually
                                suggest a change.
        @param path             Path is optional only so that
                                suggestors that have
                                been passed a list of lines
                                don't have to set the
                                path explicitly.
                                (It'll get set by the suggestor's caller.)
        """
        self.path = path
        self.start_line_number = start_line_number
        self.end_line_number = end_line_number
        self.new_lines = new_lines

        if self.end_line_number is None:
            self.end_line_number = self.start_line_number + 1
        if isinstance(self.new_lines, str):
            self.new_lines = self.new_lines.splitlines(True)

    def __repr__(self):
        return 'Patch()' % ', '.join(map(repr, [
            self.path,
            self.start_line_number,
            self.end_line_number,
            self.new_lines
        ]))

    def apply_to(self, lines):
        if self.new_lines is None:
            raise ValueError('Can\'t apply patch without suggested new lines.')
        lines[self.start_line_number:self.end_line_number] = self.new_lines

    def render_range(self):
        path = self.path or '<unknown>'
        if self.start_line_number == self.end_line_number - 1:
            return '%s:%d' % (path, self.start_line_number)
        else:
            return '%s:%d-%d' % (
                path,
                self.start_line_number, self.end_line_number - 1
            )

    def get_start_position(self):
        return Position(self.path, self.start_line_number)
    start_position = property(get_start_position)


def print_patch(patch, lines_to_print, file_lines=None):
    if file_lines is None:
        file_lines = list(open(patch.path))

    size_of_old = patch.end_line_number - patch.start_line_number
    size_of_new = len(patch.new_lines) if patch.new_lines else 0
    size_of_diff = size_of_old + size_of_new
    size_of_context = max(0, lines_to_print - size_of_diff)
    size_of_up_context = int(size_of_context / 2)
    size_of_down_context = int(ceil(size_of_context / 2))
    start_context_line_number = patch.start_line_number - size_of_up_context
    end_context_line_number = patch.end_line_number + size_of_down_context

    def print_file_line(line_number):  # noqa
        # Why line_number is passed here?
        print('  %s' % file_lines[i], end='') if (
            0 <= i < len(file_lines)) else '~\n',

    for i in range(start_context_line_number, patch.start_line_number):
        print_file_line(i)
    for i in range(patch.start_line_number, patch.end_line_number):
        if patch.new_lines is not None:
            terminal_print('- %s' % file_lines[i], color='RED')
        else:
            terminal_print('* %s' % file_lines[i], color='YELLOW')
    if patch.new_lines is not None:
        for line in patch.new_lines:
            terminal_print('+ %s' % line, color='GREEN')
    for i in range(patch.end_line_number, end_context_line_number):
        print_file_line(i)


yes_to_all = False


def _ask_about_patch(patch, editor, default_no):
    global yes_to_all
    default_action = 'n' if default_no else 'y'
    terminal_clear()
    terminal_print('%s\n' % patch.render_range(), color='WHITE')
    print()

    lines = list(open(patch.path))
    size = list(terminal_get_size())
    print_patch(patch, size[0] - 20, lines)

    print()

    if patch.new_lines is not None:
        if not yes_to_all:
            if default_no:
                print('Accept change (y = yes, n = no [default], e = edit, ' +
                      'A = yes to all, E = yes+edit, q = quit)? '),
            else:
                print('Accept change (y = yes [default], n = no, e = edit, ' +
                      'A = yes to all, E = yes+edit, q = quit)? '),
            p = _prompt('yneEAq', default=default_action)
        else:
            p = 'y'
    else:
        print('(e = edit [default], n = skip line, q = quit)? ', end=" ")
        p = _prompt('enq', default='e')

    if p in 'A':
        yes_to_all = True
        p = 'y'
    if p in 'yE':
        patch.apply_to(lines)
        _save(patch.path, lines)
    if p in 'eE':
        run_editor(patch.start_position, editor)
    if p in 'q':
        sys.exit(0)


def _prompt(letters='yn', default=None):
    """
    Wait for the user to type a character (and hit Enter).  If the user enters
    one of the characters in `letters`, return that character.  If the user
    hits Enter without entering a character, and `default` is specified,
    returns `default`.  Otherwise, asks the user to enter a character again.
    """
    while True:
        try:
            input_text = sys.stdin.readline().strip()
        except KeyboardInterrupt:
            sys.exit(0)
        if input_text and input_text in letters:
            return input_text
        if default is not None and input_text == '':
            return default
        print('Come again?')


def _save(path, lines):
    file_w = open(path, 'w')
    for line in lines:
        file_w.write(line)
    file_w.close()


def run_editor(position, editor=None):
    editor = editor or os.environ.get('EDITOR') or 'vim'
    os.system('%s +%d %s' % (editor, position.line_number + 1, position.path))


#
# Bookmarking functions.  codemod saves a file called .codemod.bookmark to
# keep track of where you were the last time you exited in the middle of
# an interactive sesh.
#

def _save_bookmark(position):
    file_w = open('.codemod.bookmark', 'w')
    file_w.write(str(position))
    file_w.close()


def _load_bookmark():
    try:
        bookmark_file = open('.codemod.bookmark')
    except IOError:
        return None
    contents = bookmark_file.readline().strip()
    bookmark_file.close()
    return Position(contents)


def _delete_bookmark():
    try:
        os.remove('.codemod.bookmark')
    except OSError:
        pass  # file didn't exist


#
# Functions for working with the terminal.  Should probably be moved to a
# standalone library.
#

def terminal_get_size(default_size=(25, 80)):
    """
    Return (number of rows, number of columns) for the terminal,
    if they can be determined, or `default_size` if they can't.
    """

    def ioctl_gwinsz(fd):  # TABULATION FUNCTIONS
        try:  # Discover terminal width
            import fcntl
            import termios
            import struct
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
            size = (os.environ.get('LINES'), os.environ.get('COLUMNS'))
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
    import curses
    curses.setupterm()
    capability = curses.tigetstr(capability_name)
    capability = unicode(capability, 'ascii')
    if capability:
        sys.stdout.write(capability)
    return bool(capability)


def terminal_print(text, color):
    """Print text in the specified color, without a terminating newline."""
    _terminal_set_color(color)
    print(text, end='')
    _terminal_restore_color()


def _terminal_set_color(color):
    import curses

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
        code = unicode(code, 'ascii')
        sys.stdout.write(code)


def _terminal_restore_color():
    import curses
    sys.stdout.write(unicode(curses.tigetstr('sgr0'), 'ascii'))

#
# Code to make this run as an executable from the command line.
#


def _parse_command_line():
    global yes_to_all

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(r"""
            codemod.py is a tool/library to assist you with large-scale
            codebase refactors
            that can be partially automated but still require
            human oversight and
            occassional intervention.

            Example: Let's say you're deprecating your use
            of the <font> tag.  From the
            command line, you might make progress by running:

              codemod.py -m -d /home/jrosenstein/www --extensions php,html \
                         '<font *color="?(.*?)"?>(.*?)</font>' \
                         '<span style="color: \1;">\2</span>'

            For each match of the regex, you'll be shown a colored diff,
            and asked if you
            want to accept the change (the replacement of
                                       the <font> tag with a <span>
            tag), reject it, or edit the line in question
            in your $EDITOR of choice.
            """),
        epilog=textwrap.dedent(r"""
            You can also use codemod for transformations that are much
            more sophisticated
            than regular expression substitution.  Rather than using
            the command line, you
            write Python code that looks like:

              import codemod
              codemod.Query(...).run_interactive()

            See the documentation for the Query class for details.

            @author Justin Rosenstein
            """)
    )

    parser.add_argument('-m', action='store_true',
                        help='Have regex work over multiple lines '
                             '(e.g. have dot match newlines). '
                             'By default, codemod applies the regex one '
                             'line at a time.')
    parser.add_argument('-d', action='store', type=str, default='.',
                        help='The path whose descendent files '
                             'are to be explored. '
                             'Defaults to current dir.')
    parser.add_argument('-i', action='store_true',
                        help='Perform case-insensitive search.')

    parser.add_argument('--start', action='store', type=str,
                        help='A path:line_number-formatted position somewhere'
                             ' in the hierarchy from which to being exploring,'
                             'or a percentage (e.g. "--start 25%%") of '
                             'the way through to start.'
                             'Useful if you\'re divvying up the '
                             'substitution task across multiple people.')
    parser.add_argument('--end', action='store', type=str,
                        help='A path:line_number-formatted position '
                             'somewhere in the hierarchy just *before* '
                             'which we should stop exploring, '
                             'or a percentage of the way through, '
                             'just before which to end.')

    parser.add_argument('--extensions', action='store',
                        default='*', type=str,
                        help='A comma-delimited list of file extensions '
                             'to process. Also supports Unix pattern '
                             'matching.')
    parser.add_argument('--include-extensionless', action='store_true',
                        help='If set, this will check files without '
                        'an extension, along with any matching file '
                        'extensions passed in --extensions')
    parser.add_argument('--exclude-paths', action='store', type=str,
                        help='A comma-delimited list of paths to exclude.')

    parser.add_argument('--accept-all', action='store_true',
                        help='Automatically accept all '
                             'changes (use with caution).')

    parser.add_argument('--default-no', action='store_true',
                        help='If set, this will make the default '
                             'option to not accept the change.')

    parser.add_argument('--editor', action='store', type=str,
                        help='Specify an editor, e.g. "vim" or emacs". '
                        'If omitted, defaults to $EDITOR environment '
                        'variable.')
    parser.add_argument('--count', action='store_true',
                        help='Don\'t run normally.  Instead, just print '
                             'out number of times places in the codebase '
                             'where the \'query\' matches.')
    parser.add_argument('match', nargs='?', action='store', type=str,
                        help='Regular expression to match.')
    parser.add_argument('subst', nargs='?', action='store', type=str,
                        help='Substitution to replace with.')

    arguments = parser.parse_args()
    if not arguments.match:
        parser.exit(0, parser.format_usage())

    yes_to_all = arguments.accept_all

    query_options = {}

    query_options['suggestor'] = (
        multiline_regex_suggestor if arguments.m else regex_suggestor
    )(arguments.match, arguments.subst, arguments.i)

    query_options['start'] = arguments.start
    query_options['end'] = arguments.end
    query_options['root_directory'] = arguments.d
    query_options['inc_extensionless'] = arguments.include_extensionless

    if arguments.exclude_paths is not None:
        exclude_paths = arguments.exclude_paths.split(',')
    else:
        exclude_paths = None
    query_options['path_filter'] = path_filter(arguments.extensions.split(','),
                                               exclude_paths)

    options = {}
    options['query'] = Query(**query_options)
    if arguments.editor is not None:
        options['editor'] = arguments.editor
    options['just_count'] = arguments.count
    options['default_no'] = arguments.default_no

    return options


def main():
    options = _parse_command_line()
    run_interactive(**options)


if __name__ == '__main__':
    main()
