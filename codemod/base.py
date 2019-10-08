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
import os
import re
import sys
import textwrap
from math import ceil

from codemod.patch import Patch
from codemod.position import Position
from codemod.query import Query
import codemod.helpers as helpers
import codemod.terminal_helper as terminal

yes_to_all = False
if sys.version_info[0] >= 3:
    unicode = str


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
    global yes_to_all

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
            terminal.terminal_move_to_beginning_of_line()
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
        terminal.terminal_clear()
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
            regex = re.compile(regex, re.DOTALL | re.MULTILINE)
        else:
            regex = re.compile(regex, re.DOTALL | re.MULTILINE | re.IGNORECASE)

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
            delta = 1 if new_lines is None else min(1, len(new_lines))
            pos = match.start() + delta

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
            terminal.terminal_print('- %s' % file_lines[i], color='RED')
        else:
            terminal.terminal_print('* %s' % file_lines[i], color='YELLOW')
    if patch.new_lines is not None:
        for line in patch.new_lines:
            terminal.terminal_print('+ %s' % line, color='GREEN')
    for i in range(patch.end_line_number, end_context_line_number):
        print_file_line(i)


def _ask_about_patch(patch, editor, default_no):
    global yes_to_all

    default_action = 'n' if default_no else 'y'
    terminal.terminal_clear()
    terminal.terminal_print('%s\n' % patch.render_range(), color='WHITE')
    print()

    lines = list(open(patch.path))
    size = list(terminal.terminal_get_size())
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
              query = codemod.Query(...)
              run_interactive(query)

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

    query_options = {}
    yes_to_all = arguments.accept_all

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
    query_options['path_filter'] = helpers.path_filter(
        arguments.extensions.split(','),
        exclude_paths
    )

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
