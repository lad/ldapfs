
"""A naming abstraction supporting LDAP DNs and file system paths."""

import os
import logging
import ldap
from .exceptions import InvalidDN

LOG = logging.getLogger(__name__)


class Path(object):
    """An abstraction for the file system paths passed to FUSE API methods."""

    def __init__(self, fspath, hosts):
        self.fspath = fspath
        self.dirpart, self.filepart = os.path.split(fspath)

        self.parts = fspath.strip('{} '.format(os.path.sep)).split(os.path.sep)
        self.len = len(self.parts)
        if self.len >= 1 and self.parts[0] in hosts:
            self.host = self.parts[0]
            if self.len >= 2 and self.parts[1] in hosts[self.host]['base_dns']:
                self.base_dn = self.parts[1]
                self.dn_parts = self.parts[1:][:]
            else:
                self.base_dn = None
                self.dn_parts = []
        else:
            self.host = None
            self.base_dn = None
            self.dn_parts = []

    def __nonzero__(self):
        return self.len != 0

    def is_root_path(self):
        """Does path represent the root file system path?"""
        return self.parts == ['']

    def has_host_part(self):
        """Does the path's first component match a configured host?"""
        return self.host is not None

    def has_base_dn_part(self):
        """Does the path's second component match a configured base-dn?"""
        return self.base_dn is not None


class DN(object):
    """An abstraction of an LDAP DN."""

    def __init__(self, parts):
        self.parts = parts
        if parts:
            self.dn = DN.unescape_path(','.join(reversed(parts)))
            # use this as validate dn - raises ldap.DECODING_ERROR on error
            try:
                ldap.dn.explode_dn(self.dn)
            except ldap.DECODING_ERROR:
                raise InvalidDN('Invalid DN={}'.format(self.dn))
        else:
            self.dn = None

    def __str__(self):
        return self.dn

    @staticmethod
    def create(parts):
        """Return a DN instance or None if the resulting dn is not valid."""
        try:
            return DN(parts)
        except InvalidDN:
            return None

    @staticmethod
    def create_parent(parts):
        """Return a DN instance or None if the parent dn is not valid."""
        pparts = len(parts) > 1 and parts[:-1] or []
        try:
            return DN(pparts)
        except InvalidDN:
            return None

    @staticmethod
    def to_filename(dn, parent_dn):
        """Convert the given DN to a filename."""
        path = dn.split(parent_dn)[0]
        # If the path ends with a non-escaped "," character chop it off
        if path.endswith(',') and not (len(path) >= 2 and path[-2] == '\\'):
            path = path[:-1]
        path = DN.escape_path(path)
        return path

    @staticmethod
    def escape_path(path):
        """Escape any characters that may cause confusion to the FS.

        File systems don't like to have the path separator in filenames
        (for obvious reasons). LDAP object names have no such restriction
        however. So here we convert path separators to %2F. Here we need to do
        the opposite and convert back.
        """
        return path.replace(os.path.sep, '%%-path-sep-%%')

    @staticmethod
    def unescape_path(path):
        """Unescape characters from previously escaped path."""
        return path.replace('%%-path-sep-%%', os.path.sep)
