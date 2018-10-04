from codemod.position import Position


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
    >>> print(p)
    Patch('x.php', 2, 4, ['X', 'Y', 'Z'])
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
        return 'Patch(%s)' % ', '.join(map(repr, [
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
