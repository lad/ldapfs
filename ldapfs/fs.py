
"""Fuse Stat structure for LdapFS."""

import fuse
import stat
from time import time
import logging

LOG = logging.getLogger(__name__)


# pylint: disable-msg=R0903
class Stat(fuse.Stat):
    """Abstraction for file stat derived from fuse.Stat
    """
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

    def __init__(self, isdir=True, dct=None, lst=None):
        fuse.Stat.__init__(self)
        if isdir:
            size = self.DIR_SIZE
        else:
            size = (dct and self._dict_size(dct) or 0) + (lst and self._list_size(lst) or 0)
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
        return '|'.join(['{}={}'.format(k, getattr(self, k)) for k in Stat.ATTRS])

    @staticmethod
    def _dict_size(attr_dct):
        """Return the file size needed to represent the given dictionary.

        The file size is the sum of the sizes for each entry in the dictionary.
        Each entry size is the length of the key + 1 for an equals + the size of
        the value. The value is assumed to be a list of items as required by
        _list_size below. The value includes space for a trailing newline.
        """
        LOG.debug('ENTER: attr_dct={}'.format(attr_dct))
        entry_sum = sum([len(key) + 1 + Stat._list_size(vals) for key, vals in attr_dct.iteritems()])
        LOG.debug('sum={}'.format(entry_sum))
        return entry_sum

    @staticmethod
    def _list_size(lst):
        """Return the file size needed to represent the given list of items.

        The size returned is sum of the lengths of each item in the list + a
        comma between each item in the list + a newline.
        """
        LOG.debug('ENTER: lst={}'.format(lst))
        size = sum([len(val) for val in lst])
        # This accounts for the commas that we'll use between values + a newline ('\n')
        size += len(lst)
        LOG.debug('size={}'.format(size))
        return size

    @staticmethod
    def size2blocks(size):
        """Return the number of file system blocks needed for the given size."""
        return (size + Stat.BLOCK_SIZE - 1) / Stat.BLOCK_SIZE
