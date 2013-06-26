#!/usr/bin/python

from setuptools import setup, find_packages

__version__ = '0.9'
__author__="Louis Dunne"
__author_email="louisadunne+ldapfs@gmail.com"
__url__ = 'http://pypi.python.org/pypi/ldapfs/'
__description__ = 'Fuse based LDAP File System'
__long_description__ = __description__

__install_requires__ = ['python-ldap', 'fuse-python', 'mock', 'coverage',
                        'pytest', 'pytest-cov']
__scripts__ = ['bin/ldapfsd']
__data_files__ = [('etc/ldapfs', ['etc/ldapfs.cfg'])]


def run():
    setup(
        name='ldapfs',
        version=__version__,
        description=__description__,
        long_description=__long_description__,
        license='Apache 2.0',
        author='Louis A. Dunne',
        author_email='louisadunne@gmail.com',
        packages=find_packages(),
        zip_safe=False,
        classifiers=[
            'Development Status :: 2 - Pre-Alpha',
            'License :: OSI Approved :: Apache Software License',
            'Intended Audience :: Developers',
            'Operating System :: POSIX :: Linux',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
            'Environment :: No Input/Output (Daemon)',
            'Programming Language :: Python :: Implementation :: CPython',
            'Topic :: Software Development :: Libraries :: Python Modules',
            'Topic :: System :: Filesystems',
            'Topic :: System :: Systems Administration :: Authentication/Directory :: LDAP'
        ],
        scripts=__scripts__,
        data_files=__data_files__,
        install_requires=__install_requires__,
        url=__url__
    )

if __name__ == '__main__':
    run()
