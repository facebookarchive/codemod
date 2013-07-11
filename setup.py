from setuptools import setup

setup(
    name='codemod',
    version='0.1',
    url='http://github.com/facebook/codemod',
    scripts=['src/codemod.py'],
    author='facebook',
    description="""Codemod is a tool/library to assist you with large-scale codebase refactors that can be partially automated but still require human oversight and occasional intervention. Codemod was developed at Facebook and released as open source.""",
    zip_safe=False,
)
