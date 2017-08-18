import os
import sys

from codemod.position import Position
import codemod.helpers as helpers


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
                 path_filter=helpers.path_filter(
                     extensions=['php', 'phpt', 'js', 'css', 'rb', 'erb']
                 ),
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
            (self.inc_extensionless and helpers.is_extensionless(path))
        )
        for path in path_list:
            try:
                lines = list(open(path))
            except (IOError, UnicodeDecodeError):
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
