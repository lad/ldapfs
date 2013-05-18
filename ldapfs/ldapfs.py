#!/usr/bin/env python

"""An LDAP backed file system using Fuse.

Usage: ldapfs.py -o config=<config-file-path> <mountpoint>

To unmount: fusermount -u <mountpoint>
"""

import os
import sys
import errno
import fuse
import logging
import ldap
import pprint

from .ldap_config_file import ConfigError, LdapConfigFile
from . import ldapdn
from . import fs

LOG = logging.getLogger(__name__)
fuse.fuse_python_api = (0, 2)

ATTRIBUTES_FILENAME = '.attributes'


class LdapFS(fuse.Fuse):
    """LDAP backed Fuse File System."""

    DEFAULT_CONFIG = '/etc/ldapfs/ldapfs.cfg'
    REQUIRED_BASE_CONFIG = ['log_file', 'log_format', 'log_levels', 'ldap_trace_level']
    PARSE_BASE_CONFIG = [('log_levels', LdapConfigFile.parse_log_levels),
                         ('ldap_trace_level', LdapConfigFile.parse_int)]
    REQUIRED_HOST_CONFIG = ['host', 'port', 'base_dns', 'bind_dn', 'bind_password']
    PARSE_HOST_CONFIG = [('port', LdapConfigFile.parse_int), ('base_dns', LdapConfigFile.validate_dns)]

    def __init__(self, *args, **kwargs):
        """Construct an LdapFS object absed on the Fuse class.

           :raises: ConfigError, IOError
        """
        fuse.Fuse.__init__(self, *args, **kwargs)
        self.flags = 0
        self.multithreaded = 0

        # Path to the config file
        self.hosts = {}
        self.config = self.DEFAULT_CONFIG
        # Tell Fuse about our argument: -o config=<config-file>
        self.parser.add_option(mountopt='config', metavar='CONFIG', default=self.config,
                               help='Configuration filename [default: {}'.format(self.DEFAULT_CONFIG))
        # This will set self.config if -o config=file was specified on the command line
        args = fuse.Fuse.parse(self, values=self, errex=1)

        # Sets instance vars with names from REQUIRED_BASE_CONFIG and
        # self.hosts keyed by hostname
        self._apply_config()

    def _apply_config(self):
        """Parse the config file and apply the config settings.

           :raises: ConfigError, IOError"""
        try:
            config_parser = LdapConfigFile(self.config)
        except ConfigError as ex:
            raise IOError(str(ex))

        # We should have an 'ldapfs' section common to the entire app, and
        # separate sections for each LDAP host that we are to connect to.
        config_sections = config_parser.get_sections()
        try:
            config_sections.remove('ldapfs')
        except ValueError:
            raise IOError('No "ldapfs" section found in config file. Path={}'.format(self.config))

        # Grab the 'ldapfs' section and add each config item as an attribute of this instance
        config_items = config_parser.get('ldapfs',
                                         required_config=self.REQUIRED_BASE_CONFIG,
                                         parse_config=self.PARSE_BASE_CONFIG)
        self.__dict__.update(config_items)

        # Split out the log level config and use a log file or stdout as appropriate.
        if self.log_file == '-':
            kwargs = {'stream': sys.stdout}
        else:
            kwargs = {'filename': self.log_file}

        # Configure logging and set levels
        root_log_level = self.log_levels.pop('root')
        logging.basicConfig(level=root_log_level, format=self.log_format, **kwargs)
        for module, level in self.log_levels.iteritems():
            log = logging.getLogger(module)
            log.setLevel(level)

        # Save the configuration for each host.
        for section in config_sections:
            values = config_parser.get(section, required_config=self.REQUIRED_HOST_CONFIG,
                                       parse_config=self.PARSE_HOST_CONFIG)
            key = values.pop('host')
            self.hosts[key] = values

        LOG.debug('ldapfs-config={}'.format(pprint.pformat(config_items)))
        LOG.debug('hosts-config={}'.format(pprint.pformat(self.hosts)))

    @staticmethod
    def _path2list(path):
        """Convert the given path to a list of its components."""
        return path.strip('{} '.format(os.path.sep)).split(os.path.sep)

    def fsinit(self):
        """Start the connections to the LDAP server(s).

        This is a FUSE API method invoked by FUSE before the file system
        is ready to serve requests.

        :raises: IOError
        """
        try:
            for host, values in self.hosts.iteritems():
                bind_uri = 'ldap://{}:{}'.format(host, values['port'])
                con = ldap.initialize(bind_uri, trace_level=self.ldap_trace_level)
                con.simple_bind_s(values['bind_dn'], values['bind_password'])
                values['con'] = con
        except ldap.LDAPError as ex:
            raise IOError('Error binding to {}: {}'.format(bind_uri, ex))

    def getattr(self, path):
        """Return stat structure for the given path."""
        LOG.debug('ENTER: path={}'.format(path))

        pathlst = self._path2list(path)
        LOG.debug('pathlst={}'.format(pathlst))

        if not pathlst:
            LOG.debug('Empty pathlst')
            return -errno.ENOENT
        elif pathlst == ['']:
            LOG.debug('Root path')
            return fs.Stat(isdir=True)

        # Try matching the first path component against the configured hosts

        host = pathlst[0]
        try:
            host_config = self.hosts[host]
            base_dns = host_config['base_dns']
        except KeyError:
            LOG.debug('No config found for host={} for path={}'.format(host, path))
            return -errno.ENOENT

        LOG.debug('host_config={}'.format(host_config))

        len_pathlst = len(pathlst)
        if len_pathlst == 1:
            # No more path components to look at - we're done
            return fs.Stat(isdir=True)

        # Try matching the second path component against the configured base-dns

        base_dn = pathlst[1]
        if base_dn not in base_dns:
            LOG.debug('No base_dn={} found for host={} for path={}'.format(base_dn, host, path))
            return -errno.ENOENT

        con = host_config['con']

        # Now we need to find an object that matches the remaining path (without the
        # leading host and base-dn)

        try:
            dn = ldapdn.list2dn(pathlst[2:], base_dn)
            LOG.debug('search_st({}, {}, attrsonly)'.format(dn, ldap.SCOPE_BASE))
            con.search_st(dn, ldap.SCOPE_BASE, attrsonly=1)
            # We found a matching LDAP object. We're done.
            return fs.Stat(isdir=True)
        except ldap.DECODING_ERROR:
            LOG.debug('Invalid dn from path={}. Check for attribute on parent'.format(path))
            # Fallthrough and continue below...
        except (ldap.NO_SUCH_OBJECT, ldap.INVALID_DN_SYNTAX):
            LOG.debug('dn={} not found. Check for attribute on parent'.format(dn))
            # Fallthrough and continue below...
        except ldap.LDAPError as ex:
            LOG.debug('dn={}. Exception={}'.format(dn, ex))
            return -errno.ENOENT

        # No matching LDAP object for the remaining path.

        if len_pathlst == 2:
            LOG.debug('Path exhausted - not checking for attribute on parent.')
            return -errno.ENOENT

        # Try looking for an attribute on this path's parent

        try:
            parent_path_lst, filename = pathlst[2:-1], pathlst[-1]      # split?
            parent_dn = ldapdn.list2dn(parent_path_lst, base_dn)

            LOG.debug('search_st({}, {})'.format(parent_dn, ldap.SCOPE_BASE))
            entry = con.search_st(parent_dn, ldap.SCOPE_BASE)
            dct = entry[0][1]
        except ldap.DECODING_ERROR:
            LOG.debug('Invalid DN from parent-path-lst={} base-dn={} for path={}'.format(
                     parent_path_lst, base_dn, path))
            return -errno.ENOENT
        except ldap.NO_SUCH_OBJECT:
            LOG.debug('parent_dn={} not found'.format(parent_dn))
            return -errno.ENOENT
        except ldap.LDAPError as ex:
            LOG.debug('parent_dn={}. Exception={}'.format(parent_dn, ex))
            return -errno.ENOENT

        # Check if the filename part matches the special file ".attributes"
        if filename == ATTRIBUTES_FILENAME:
            LOG.debug('Return {}'.format(ATTRIBUTES_FILENAME))
            return fs.Stat(isdir=False, size=fs.entry_size(dct))
        else:
            # We have the parent object. Check if there's an attribute with the
            # same name as the input filename
            attr = dct.get(filename)
            if attr:
                LOG.debug('PARENT-ENTRY={}'.format(entry))
                return fs.Stat(isdir=False, size=fs.attr_size(attr))
            else:
                LOG.debug('Attribute={} not found in parent-dn={} for path={}'.format(filename, parent_dn, path))
                return -errno.ENOENT

    def readdir(self, path, offset):
        """Read the given directory path and yield its contents."""
        LOG.debug('ENTER: path={} offset={}'.format(path, offset))
        dirents = ['.', '..']

        pathlst = self._path2list(path)
        LOG.debug('pathlst={}'.format(pathlst))
        if not pathlst:
            return
        elif pathlst == ['']:
            dirents.extend(self.hosts.keys())
            LOG.debug('Added hosts to dirents={}'.format(dirents))
        else:
            host = pathlst[0]
            try:
                host_config = self.hosts[host]
                base_dns = host_config['base_dns']
            except KeyError:
                LOG.debug('No config found for host={} for path={}'.format(host, path))
                return

            LOG.debug('host_config={}'.format(host_config))

            if len(pathlst) == 1:
                dirents.extend(base_dns)
            else:
                base_dn = pathlst[1]
                if base_dn not in base_dns:
                    LOG.debug('No base dn={} found in configured base dns={} for host={} for path={}'.format(
                            base_dn, base_dns, host, path))
                    return

                dirents.append(ATTRIBUTES_FILENAME)
                con = host_config['con']

                try:
                    dn = ldapdn.list2dn(pathlst[2:], base_dn)
                    base = con.search_st(dn, ldap.SCOPE_BASE, attrsonly=1)
                    dirents.extend(base[0][1].keys())

                    entries = con.search_st(dn, ldap.SCOPE_ONELEVEL, attrsonly=1)
                    dirents.extend([ldapdn.dn2filename(entry[0], dn) for entry in entries])
                except ldap.DECODING_ERROR:
                    LOG.debug('Invalid DN from lst={} base-dn={} for path={}'.format(pathlst[2:-1], base_dn, path))
                    return
                except ldap.LDAPError as ex:
                    LOG.error('Error reading dn={} for path={}. {}'.format(dn, path, ex))
                    return

        for ent in dirents:
            LOG.debug('readdir: yield {}'.format(ent))
            yield fuse.Direntry(ent)

    # pylint: disable-msg=R0201
    def mknod(self, path, mode, dev):
        """Create a file entry at the given path with the given mode."""
        LOG.debug('ENTER: path={} mode={} dev={}'.format(path, mode, dev))
        return 0

    # pylint: disable-msg=R0201
    def unlink(self, path):
        """Remove the file entry at the given path."""
        LOG.debug('ENTER: path={}'.format(path))
        return 0

    def read(self, path, size, offset):
        """Read the file entry at the given path, size and offset."""
        LOG.debug('ENTER: path={} size={} offset={}'.format(path, size, offset))

        pathlst = self._path2list(path)
        LOG.debug('pathlst={}'.format(pathlst))
        len_pathlst = len(pathlst)
        if len_pathlst < 3:
            # There are no files in the first two directories (host/base-dn) so any attempt
            # to read paths with only two components must be wrong.
            return -errno.ENOENT

        host = pathlst[0]
        try:
            host_config = self.hosts[host]
            base_dns = host_config['base_dns']
            LOG.debug('host_config={}'.format(host_config))
        except KeyError:
            LOG.debug('No config found for host={} for path={}'.format(host, path))
            return -errno.ENOENT

        base_dn = pathlst[1]
        if base_dn not in base_dns:
            LOG.debug('No base_dn={} found for host={} for path={}'.format(base_dn, host, path))
            return -errno.ENOENT

        con = host_config['con']
        try:
            dn = ldapdn.list2dn(pathlst[2:-1], base_dn)
            LOG.debug('search_st({}, {})'.format(dn, ldap.SCOPE_BASE))
            entry = con.search_st(dn, ldap.SCOPE_BASE)
            LOG.debug('Entry={}'.format(entry))
            dct = entry[0][1]
        except ldap.DECODING_ERROR:
            LOG.debug('Invalid dn from pathlst[2:-1]={} for path={}'.format(pathlst[2:-1], path))
            return -errno.ENOENT
        except (ldap.NO_SUCH_OBJECT, ldap.INVALID_DN_SYNTAX):
            LOG.debug('dn={} not found for path={}'.format(dn, path))
            return -errno.ENOENT
        except ldap.LDAPError as ex:
            LOG.debug('dn={}. Exception={}'.format(dn, ex))
            return -errno.ENOENT

        LOG.debug('dct={}'.format(dct))

        filename = pathlst[-1]
        # Check if we're reading the '.attributes' special file
        if filename == ATTRIBUTES_FILENAME:
            # Return name=value on separate lines
            retval = '\n'.join(['{}={}'.format(key, ','.join(val)) for key, val in dct.iteritems()]) + '\n'
            return retval[offset:size]
        elif filename in dct:
            retval = ','.join(dct[filename]) + '\n'
            return retval[offset:size]
        else:
            return -errno.ENOENT

    def write(self, path, buf, offset):
        """Write to given buffer at the given path at the given offset."""
        LOG.debug('ENTER: path={} buf={} offset={}'.format(path, buf, offset))

        # TODO: Incomplete

        pathlst = self._path2list(path)
        LOG.debug('pathlist={}'.format(pathlst))
        len_pathlst = len(pathlst)
        if len_pathlst < 3:
            # There are no files in the first two directories (host/base-dn) so any attempt
            # to write paths with only two components must be wrong.
            return -errno.ENOENT

        host = pathlst[0]
        try:
            host_config = self.hosts[host]
            base_dns = host_config['base_dns']
        except KeyError:
            LOG.debug('No config found for host={} for path={}'.format(host, path))
            return -errno.ENOENT

        base_dn = pathlst[1]
        if base_dn not in base_dns:
            LOG.debug('No base_dn={} found for host={} for path={}'.format(base_dn, host, path))
            return -errno.ENOENT

        if pathlst[2] == ATTRIBUTES_FILENAME:
            LOG.debug('No write allowed to attribute file={}'.format(ATTRIBUTES_FILENAME))
            return -errno.EPERM

        #con = host_config['con']

        return 0

    # pylint: disable-msg=R0201
    def open(self, path, flags):
        """Open a file entry at the given path with the given flags."""
        LOG.debug('ENTER: path={} flags={}'.format(path, flags))
        return 0

    # pylint: disable-msg=R0201
    def release(self, path, flags):
        """Close a file entry at the given path with the given flags."""
        LOG.debug('ENTER: path={} flags={}'.format(path, flags))
        return 0

    # pylint: disable-msg=R0201
    def truncate(self, path, size):
        """Truncate the file entry at the given path to the given size."""
        LOG.debug('ENTER: path={} size={}'.format(path, size))
        return 0

    # pylint: disable-msg=R0201
    def utime(self, path, times):
        """Set the time of the entry at the given path."""
        LOG.debug('ENTER: path={} times={}'.format(path, times))
        return 0

    # pylint: disable-msg=R0201
    def mkdir(self, path, mode):
        """Create a directory entry at the given path with the given mode."""
        LOG.debug('ENTER: path={} mode={}'.format(path, mode))
        return 0

    # pylint: disable-msg=R0201
    def rmdir(self, path):
        """Remove a directory entry at the given path."""
        LOG.debug('ENTER: path={}'.format(path))
        return 0

    # pylint: disable-msg=R0201
    def rename(self, src, dst):
        """Rename a file/directory entry."""
        LOG.debug('ENTER: src={} dst={}'.format(src, dst))

        # TODO: Incomplete
        # Works in the basic +ve case when moving dirs
        # Still lots of different cases to do

        #src_dn = None
        #try:
            #src_dn = ldapdn.path2dn(src)
            #dst_rdn = ldapdn.path2rdn(dst)
            #LOG.debug('rename_s({}, {})'.format(src_dn, dst_rdn))
            #con = self.hosts[('localhost', 'dc=dunne,dc=ie')]['con']
            #con.rename_s(src_dn, dst_rdn)
        #except ldap.DECODING_ERROR:
            #if not src_dn:
                #LOG.debug('Invalid dn from src path={}'.format(src))
            #else:
                #LOG.debug('Invalid rdn from dst path={}'.format(dst))
            #return -errno.EINVAL
        #except ldap.LDAPError as ex:
            #LOG.debug('rename_s: Exception={}'.format(ex))
            #return -errno.EINVAL
        return 0

    @staticmethod
    def run():
        """Run the LdapFS server."""
        ldapfs = None
        try:
            ldapfs = LdapFS(version='%prog ' + fuse.__version__, usage='usage', dash_s_do='setsingle')
            ldapfs.main()
        except (ConfigError, OSError, IOError) as main_ex:
            LOG.error(str(main_ex))
            print main_ex


if __name__ == '__main__':
    LdapFS.run()
