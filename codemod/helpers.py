import fnmatch
import os


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
