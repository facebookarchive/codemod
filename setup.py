try:
    from setuptools import setup, find_packages
except ImportError:
    from distutils.core import setup, find_packages

description = (
    'Codemod is a tool/library to assist you with large-scale codebase '
    'refactors that can be partially automated but still require human '
    'oversight and occasional intervention. Codemod was developed at '
    'Facebook and released as open source.'
)

setup(
    name='codemod',
    version="1.0.0",
    url='http://github.com/facebook/codemod',
    license='Apache License 2.0',
    author="Facebook",
    author_email="facebook@facebook.com",
    description=description,
    long_description=description,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    entry_points='''
        [console_scripts]
        codemod=codemod.base:main
    ''',
    tests_require=['flake8', 'pytest'],
    test_suite='py.test'
)
