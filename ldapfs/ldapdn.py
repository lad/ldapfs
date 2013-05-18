"""Utility functions for manipulating LDAP Distinguished Names."""

import os
import logging
import ldap


BASE_DN = 'dc=dell,dc=com'
LOG = logging.getLogger(__name__)


def path2dn(path):
    """Convert the given path to its equivalent LDAP DN."""
    LOG.debug('ENTER: path={}'.format(path))
    path = path.strip(os.path.sep)

    # The LDAP DNs hierarchy is in the reverse order to filesystem paths
    path = ','.join(reversed(path.split(os.path.sep)))
    if path:
        dn = escape_path(path) + ',' + BASE_DN
        # use this as validate dn - raises ldap.DECODING_ERROR on error
        ldap.dn.explode_dn(dn)
        return dn
    else:
        return BASE_DN


def list2dn(pathlst, base_dn):
    """Convert the given list of path components to its equivalent LDAP DN."""
    LOG.debug('ENTER: pathlst={} base_dn={}'.format(pathlst, base_dn))

    if pathlst:
        # The LDAP DNs hierarchy is in the reverse order to filesystem paths
        path = ','.join(reversed(pathlst))
        dn = unescape_path(path) + ',' + base_dn
        # use this as validate dn - raises ldap.DECODING_ERROR on error
        ldap.dn.explode_dn(dn)
    else:
        dn = base_dn
    LOG.debug('Returning: {}'.format(dn))
    return dn


def escape_path(path):
    """Escape any characters that may cause confusion to the FS.

    Fuse gets confused if we return a filename containing a slash even if
    escaped with a preceeding '\' character. So we convert path
    separators to %2F. Here we need to do the opposite and convert back.
    """
    LOG.debug('ENTER: path={}'.format(path))
    return path.replace(os.path.sep, '%2F')


def unescape_path(path):
    """Unescape characters from previously escaped path."""
    LOG.debug('ENTER: path={}'.format(path))
    return path.replace('%2F', os.path.sep)


def path2rdn(path):
    """Convert the given path to an LDAP RDN."""
    LOG.debug('ENTER: path={}'.format(path))
    path = path.strip(os.path.sep)
    if path:
        return unescape_path(os.path.split(path)[-1])
    else:
        raise ldap.DECODING_ERROR('Invalid RDN from path={}'.format(path))


def dn2filename(dn, parent_dn):
    """Convert the given DN to a filename."""
    LOG.debug('ENTER: dn={} parent_dn={}'.format(dn, parent_dn))
    path = dn.split(parent_dn)[0]
    # If the path ends with a non-escaped "," character then chop it off
    if path.endswith(',') and not (len(path) >= 2 and path[-2] == '\\'):
        path = path[:-1]
    path = escape_path(path)
    LOG.debug('path={}'.format(path))
    return path
