
"""Fuse Stat structure for LdapFS."""

import fuse
import stat
from time import time
import logging

LOG = logging.getLogger(__name__)


def entry_size(attr_dct):
    """Return the file size needed to represent the given LDAP entry.

    The file size is the sum of the sizes for each attribute. Each
    attribute size is the length of the attribute name + 1 for an equals +
    the size of the attribute value. The size of the attribute value
    includes space for a a trailing newline."""
    LOG.debug('ENTER: attr_dct={}'.format(attr_dct))
    entry_sum = sum([len(key) + 1 + attr_size(vals) for key, vals in attr_dct.iteritems()])
    LOG.debug('sum={}'.format(entry_sum))
    return entry_sum

def attr_size(vallst):
    """Return the file size needed to represent the given attribute value.

    The size returned is sum of the lengths of each value in the attribute
    value list + a comma between each value + a newline."""
    LOG.debug('ENTER: vallst={}'.format(vallst))
    size = sum([len(val) for val in vallst])
    # This accounts for the commas that we'll use between values + a newline ('\n')
    size += len(vallst)
    LOG.debug('size={}'.format(size))
    return size



# pylint: disable-msg=R0903
class Stat(fuse.Stat):
    """Abstraction for file stat derived from fuse.Stat"""

    DIR_SIZE = 4096
    DIR_MODE = 0755 | stat.S_IFDIR
    FILE_MODE = 0644 | stat.S_IFREG
    BLOCK_SIZE = 512    # Default fuse block size
    ATTRS = {'st_mode': None,
             'st_size': None,
             'st_blocks': None,
             'st_atime': None,
             'st_mtime': None,
             'st_ctime': None,
             'st_nlink': 1,
             'st_rdev': 0,
             'st_uid': 0,
             'st_gid': 0,
             'st_dev': 0,
             'st_blksize': 0,
             'st_ino': 0}

    def __init__(self, isdir=True, size=DIR_SIZE):
        fuse.Stat.__init__(self)
        now = int(time())
        inst_dict = {'st_mode': isdir and Stat.DIR_MODE or Stat.FILE_MODE,
                     'st_size': size,
                     'st_blocks': self.size2blocks(size),
                     'st_atime': now,
                     'st_mtime': now,
                     'st_ctime': now}

        # make instance vars
        self.__dict__.update(Stat.ATTRS)
        self.__dict__.update(inst_dict)

    def __str__(self):
        return '|'.join(['{}={}'.format(k, getattr(k)) for k in Stat.ATTRS])

    @staticmethod
    def size2blocks(size):
        """Return the number of file system blocks needed for the given size."""
        return (size + Stat.BLOCK_SIZE - 1) / Stat.BLOCK_SIZE


