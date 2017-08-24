codemod
=======

[![PyPI](https://img.shields.io/pypi/v/codemod.svg)](https://pypi.python.org/pypi/codemod)
[![downloads](https://img.shields.io/pypi/dw/codemod.svg)](https://pypi.python.org/pypi/codemod)
[![Travis CI](http://img.shields.io/travis/facebook/codemod.svg)](https://travis-ci.org/facebook/codemod)
[![Code Health](https://landscape.io/github/rochacbruno/codemod/master/landscape.svg?style=flat)](https://landscape.io/github/rochacbruno/codemod/master)


Overview
--------

codemod is a tool/library to assist you with large-scale codebase refactors that can be partially automated but still require human oversight and occasional intervention.

Example: Let's say you're deprecating your use of the `<font>` tag.  From the command line, you might make progress by running:

    codemod -m -d /home/jrosenstein/www --extensions php,html \
        '<font *color="?(.*?)"?>(.*?)</font>' \
        '<span style="color: \1;">\2</span>'

For each match of the regex, you'll be shown a colored diff, and asked if you want to accept the change (the replacement of the `<font>` tag with a `<span>` tag), reject it, or edit the line in question in your `$EDITOR` of choice.

Install
-------
In a virtual environment or as admin user

`pip install codemod`

or system wide with sudo

`sudo -H pip install codemod`

Usage
-----

The last two arguments are a regular expression to match and a substitution string, respectively.  Or you can omit the substitution string, and just be prompted on each match for whether you want to edit in your editor.

Options (all optional) include:

    -m
      Have regex work over multiple lines (e.g. have dot match newlines).  By
      default, codemod applies the regex one line at a time.
    -d
      The path whose ancestor files are to be explored.  Defaults to current dir.
    -i
      Make your search case-insensitive
    --start
      A path:line_number-formatted position somewhere in the hierarchy from which
      to being exploring, or a percentage (e.g. "--start 25%") of the way through
      to start.  Useful if you're divvying up the substitution task across
      multiple people.
    --end
      A path:line_number-formatted position somewhere in the hierarchy just
      *before* which we should stop exploring, or a percentage of the way
      through, just before which to end.
    --extensions
      A comma-delimited list of file extensions to process. Also supports Unix
      pattern matching.
    --include-extensionless
      If set, this will check files without an extension, along with any
      matching file extensions passed in --extensions
    --accept-all
      Automatically accept all changes (use with caution)
    --default-no
      Set default behavior to reject the change.
    --editor
      Specify an editor, e.g. "vim" or "emacs".  If omitted, defaults to $EDITOR
      environment variable.
    --count
      Don't run normally.  Instead, just print out number of times places in the
      codebase where the 'query' matches.
    --test
      Don't run normally.  Instead, just run the unit tests embedded in the
      codemod library.

You can also use codemod for transformations that are much more sophisticated than regular expression substitution.  Rather than using the command line, you write Python code that looks like:

    import codemod
    codemod.Query(...).run_interactive()

See the documentation for the Query class for details.

Background
----------

*Announcement by Justin Rosenstein on Facebook Notes, circa December 2008*

Part of why most code -- and most software -- sucks so much is that making sweeping changes is hard.

Let's say that a month ago you wrote a function that you -- or your entire company -- have been using frequently. And now you decide to change its name, or change the order of its parameters, or split it up into two separate functions and then have half the call sites use the old one and half the call sites use the new one, or change its return type from a scalar to a structure with additional information. IDEs and standard \*nix tools like sed can help, but you typically have to make a trade-off between introducing errors and introducing tedium. The result, all too often, is that we decide (often unconsciously) that the sweeping change just isn't worth it, and leave the undesirable pattern untouched for future versions of ourselves and others to grumble about, while the pattern grows more and more endemic to the code base.

What you really want is to be able to describe an arbitrary transform -- using either regexes in the 80% case or Python code for more complex transformations -- that matches for lines (or sets of lines) of source code and converts them to something more desirable, but then have a tool that will show you each of the change sites one at a time and ask you either to accept the change, reject the change, or manually intervene using your editor of choice.

So, while at Facebook, I wrote a script that does exactly that. codemod.py a nifty little utility/library to assist with codebase refactors that can be partially automated but still require human oversight and occasional intervention. And, thanks to help from Mr. David Fetterman, codemod is now open source. Check it out (so to speak):

    git clone git://github.com/facebook/codemod.git
    (previously svn checkout https://codemod.svn.sourceforge.net/svnroot/codemod/trunk codemod)

It's one of those tools where, the more you use it, the more you think of places to use it -- and the more you realize how much you were compromising the quality of your code because reconsidering heavily-used code patterns sounded just too damn annoying. I use it pretty much every day.

Dependencies
------------

* python2

Credits
-------

Copyright (c) 2007-2008 Facebook.

Created by Justin Rosenstein.

Licensed under the Apache License, Version 2.0.

