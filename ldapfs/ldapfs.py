#!/usr/bin/env python

"""An LDAP backed file system using Fuse.

Usage: ldapfs.py -o config=<config-file-path> <mountpoint>

To unmount: fusermount -u <mountpoint>
"""


import sys
import errno
import fuse
import logging
import os
import traceback

from .exceptions import LdapfsException, LdapException, InvalidDN, NoSuchObject
from .ldapconf import LdapConfigFile
from . import ldapcon
from . import name
from . import fs
from . import trace

LOG = logging.getLogger(__name__)
fuse.fuse_python_api = (0, 2)


# pylint: disable-msg=R0904
# - Disable "too many public methods"
# - this is the FUSE API not under our control
class LdapFS(fuse.Fuse):
    """LDAP backed Fuse File System."""

    DEFAULT_CONFIG = '/etc/ldapfs/ldapfs.cfg'
    REQUIRED_BASE_CONFIG = ['log_file', 'log_format', 'log_levels']
    PARSE_BASE_CONFIG = [('log_levels', LdapConfigFile.parse_log_levels)]
    REQUIRED_HOST_CONFIG = ['host', 'port', 'base_dns', 'bind_dn',
                            'bind_password', 'ldap_trace_level']
    PARSE_HOST_CONFIG = [('port', LdapConfigFile.parse_int),
                         ('base_dns', LdapConfigFile.validate_dns),
                         ('ldap_trace_level', LdapConfigFile.parse_int)]

    def __init__(self, *args, **kwargs):
        """Construct an LdapFS object absed on the Fuse class.

           :raises: ConfigError, fuse.FuseError
        """
        fuse.Fuse.__init__(self, *args, **kwargs)
        self.flags = 0              # for fuse
        self.multithreaded = 0      # for fuse
        self.ldap = None            # all ldap server interaction
        self.hosts = {}             # maps hostname to host config
        self.trace_file = None      # trace program execution (optional)

        # Path to the config file
        self.config = self.DEFAULT_CONFIG
        # Tell Fuse about our argument: -o config=<config-file>
        self.parser.add_option(mountopt='config', metavar='CONFIG',
                               default=self.config,
                               help='Configuration filename [default: {}'
                                    .format(self.DEFAULT_CONFIG))
        # This will set self.config if -o config=file was specified on the
        # command line
        args = fuse.Fuse.parse(self, values=self, errex=1)

        # Sets instance vars with names from REQUIRED_BASE_CONFIG and
        # self.hosts keyed by hostname
        self._apply_config()

    def _apply_config(self):
        """Parse the config file and apply the config settings.

           :raises: ConfigError
        """
        config_parser = LdapConfigFile(self.config)

        # Grab the 'ldapfs' section and add each config item as an attribute of
        # this instance
        config_items = config_parser.get('ldapfs',
                                    required_config=self.REQUIRED_BASE_CONFIG,
                                    parse_config=self.PARSE_BASE_CONFIG)

        self.trace_file = config_items.get('trace_file')
        if self.trace_file:
            trace.start(self.trace_file, os.path.dirname(__file__))

        # Split out the log level config and use a log file or stdout as
        # appropriate.
        if config_items['log_file'] == '-':
            destination = {'stream': sys.stdout}
        else:
            destination = {'filename': config_items['log_file']}

        # Configure logging and set levels
        root_log_level = config_items['log_levels'].pop('root')
        logging.basicConfig(level=root_log_level,
                            format=config_items['log_format'],
                            **destination)
        for module, level in config_items['log_levels'].iteritems():
            log = logging.getLogger(module)
            log.setLevel(level)

        # setup to log uncaught exceptions
        sys.excepthook = self.log_uncaught_exceptions

        # We should have an 'ldapfs' section common to the entire app (parsed
        # above), and separate sections for each LDAP host that we are to
        # connect to.
        config_sections = config_parser.get_sections()
        config_sections.remove('ldapfs')

        # Save the configuration for each host.
        for section in config_sections:
            values = config_parser.get(section,
                                    required_config=self.REQUIRED_HOST_CONFIG,
                                    parse_config=self.PARSE_HOST_CONFIG)
            key = values.pop('host')
            self.hosts[key] = values

        self.ldap = ldapcon.Connection(self.hosts)

    @staticmethod
    def log_uncaught_exceptions(ex_cls, ex, tb):
        """Except hook - called for any uncaught exceptions."""
        LOG.critical(''.join(traceback.format_tb(tb)))
        LOG.critical('{}: {}'.format(ex_cls, ex))

    def fsinit(self):
        """Start the connections to the LDAP server(s).

        This is a FUSE API method invoked by FUSE before the file system
        is ready to serve requests. Sadly when an exception is raised
        here Python Fuse doesn't exit. Raising SystemExit or calling
        sys.exit() does cause the process to exit but leaves the mount
        in place forcing a cleanup with fusermount -u.

        :raises: LdapException
        """
        LOG.debug('File system starting...')
        self.ldap.open()

    def fsdestroy(self):
        """Shutdown the connections to the LDAP server(s)."""
        LOG.debug('File system stopping...')
        self.ldap.close()
        if self.trace_file:
            trace.stop()

    # pylint: disable-msg=R0911,R0912
    # - pylint doesn't like the number of return statements or branches in
    #   this method
    # - I think the logic is represented more cleanly by having multiple
    #   returns and branches here.
    def getattr(self, fspath):
        """Return stat structure for the given path."""
        path = name.Path(fspath, self.hosts)
        if not path:
            LOG.debug('Empty path')
            return -errno.ENOENT
        elif path.is_root_path():
            LOG.debug('Root path')
            return fs.Stat(isdir=True)

        if not path.has_host_part():
            LOG.debug("path doesn't match any configured hosts: {}"
                      .format(fspath))
            return -errno.ENOENT

        if path.len == 1:
            # No more path components to look at - we're done
            return fs.Stat(isdir=True)

        if not path.has_base_dn_part():
            LOG.debug("path doesn't match any configured base DNs for host={} "
                      "path={}".format(path.host, fspath))
            return -errno.ENOENT

        # Now we need to find an object that matches the remaining path
        # (without the leading host and base-dn)

        dn = name.DN.create(path.dn_parts)            
        try:
            if dn and self.ldap.exists(path.host, dn):
                # We found a matching LDAP object. We're done.
                return fs.Stat(isdir=True)
        except ldapcon.LdapException as ex:
            LOG.debug('Exception from ldap.exists for dn={} for fspath={}. {}'
                      .format(dn, fspath, ex))
            return -errno.ENOENT

        if path.len == 2:
            LOG.debug('Path exhausted - not checking for attribute on parent.')
            return -errno.ENOENT

        # Try looking for an attribute on this path's parent

        try:
            parent_dn = name.DN.create_parent(path.dn_parts)
            if not parent_dn:
                LOG.debug('Invalid parent DN for fspath={}'.format(fspath))
                return -errno.ENOENT

            entry = self.ldap.get(path.host, parent_dn)
        except ldapcon.NoSuchObject:
            LOG.debug('parent_dn={} not found for fspath={}'.format(parent_dn,
                                                                    fspath))
            return -errno.ENOENT
        except ldapcon.LdapException as ex:
            LOG.debug('Exception from ldap.get for parent_dn={} for '
                      'fspath={} {}'.format(parent_dn, fspath, ex))
            return -errno.ENOENT

        try:
            return fs.Stat(isdir=False, size=entry.size(path.filepart))
        except AttributeError:
            return -errno.ENOENT

    def readdir(self, fspath, _):
        """Read the given directory path and yield its contents."""
        dir_entries = ['.', '..']

        path = name.Path(fspath, self.hosts)
        if not path:
            return
        elif path.is_root_path():
            LOG.debug('Root path')
            dir_entries.extend(self.hosts.keys())
        else:
            if not path.has_host_part():
                LOG.debug("path doesn't match any configured hosts: {}"
                          .format(fspath))
                return

            if path.len == 1:
                # root dir has a list of the base dns
                dir_entries.extend(self.hosts[path.host]['base_dns'])
            else:
                if not path.has_base_dn_part():
                    LOG.debug("path doesn't match any configured base DNs for "
                              "host={} path={}".format(path.host, fspath))
                    return

                # Each dir has a .attributes file that contains all attributes
                # for that LDAP object that the current dir is representing
                dir_entries.append(ldapcon.Entry.ALL_ATTRIBUTES)

                try:
                    dn = name.DN(path.dn_parts)
                    base = self.ldap.get(path.host, dn, attrsonly=True)
                    # Each attribute of the LDAP object is represented as a
                    # directory entry. A later getattr() call on these names
                    # will tell Fuse that these are files.
                    dir_entries.extend(base.names())

                    entries = self.ldap.search(path.host, dn, recur=False,
                                               attrsonly=True)
                    dir_entries.extend([name.DN.to_filename(entry.dn, str(dn))
                                       for entry in entries])
                except InvalidDN:
                    LOG.debug('Invalid DN for fspath={}'.format(fspath))
                    return
                except LdapException as ex:
                    LOG.error('Error reading dn={} for fspath={}. {}'
                              .format(dn, fspath, ex))
                    return

        for ent in dir_entries:
            LOG.debug('yield {}'.format(ent))
            yield fuse.Direntry(ent)

    def read(self, fspath, size, offset):
        """Read the file entry at the given path, size and offset."""
        path = name.Path(fspath, self.hosts)
        if path.len < 3:
            # There are no files in the first two directories (host/base-dn)
            return -errno.ENOENT

        if not path.has_host_part():
            LOG.debug("path doesn't match any configured hosts: {}"
                      .format(fspath))
            return -errno.ENOENT

        if not path.has_base_dn_part():
            LOG.debug("path doesn't match any configured base DNs for host={} "
                      "path={}".format(path.host, fspath))
            return -errno.ENOENT

        try:
            # Look for an LDAP object matching the directory name
            dn = name.DN.create_parent(path.dn_parts)
            entry = self.ldap.get(path.host, dn)
            LOG.debug('Entry={}'.format(entry))
        except InvalidDN:
            LOG.debug('Invalid dn from fspath={}'.format(fspath))
            return -errno.ENOENT
        except NoSuchObject:
            LOG.debug('dn={} not found for fspath={}'.format(dn, fspath))
            return -errno.ENOENT
        except LdapException as ex:
            LOG.debug('Exception from ldap.get for dn={} for fspath={}. {}'
                      .format(dn, fspath, ex))
            return -errno.ENOENT

        try:
            return entry.text(path.filepart)[offset:size]
        except AttributeError:
            return -errno.ENOENT

    def main(self, *args):
        try:
            fuse.Fuse.main(self, *args)
        finally:
            if self.trace_file:
                trace.stop()

    @staticmethod
    def run():
        """Run the LdapFS server."""
        try:
            LdapFS(version='%prog ' + fuse.__version__, usage='usage',
                            dash_s_do='setsingle').main()
        except (LdapfsException, fuse.FuseError) as main_ex:
            LOG.error(str(main_ex))
            print main_ex


if __name__ == '__main__':
    LdapFS.run()
