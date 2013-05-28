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
        self.flags = 0
        self.multithreaded = 0
        self.ldap = None
        self.hosts = {}
        self.trace_file = None
        self.dirs = {}

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
            kwargs = {'stream': sys.stdout}
        else:
            kwargs = {'filename': config_items['log_file']}

        # Configure logging and set levels
        root_log_level = config_items['log_levels'].pop('root')
        logging.basicConfig(level=root_log_level,
                            format=config_items['log_format'],
                            **kwargs)
        for module, level in config_items['log_levels'].iteritems():
            log = logging.getLogger(module)
            log.setLevel(level)

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

    def fsinit(self):
        """Start the connections to the LDAP server(s).

        This is a FUSE API method invoked by FUSE before the file system
        is ready to serve requests. Sadly when an exception is raised
        here Python Fuse doesn't exit. Raising SystemExit or calling
        sys.exit() does cause the process to exit but leaves the mount
        in place forcing a cleanup with fusermount -u.

        :raises: LdapException
        """
        self.ldap.connect()

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

        LOG.debug('DIRS={} FILEPART={} DIRPART={}'.format(self.dirs, path.filepart, path.dirpart))
        if path.filepart in self.dirs.get(path.dirpart, []):
            return fs.Stat(isdir=True)

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

                if not self.dirs.get(path.dirpart):
                    # Each dir has a .attributes file that contains all
                    # attributes for that LDAP object that the current dir is
                    # representing
                    dir_entries.append(ldapcon.Entry.ALL_ATTRIBUTES)

                    try:
                        dn = name.DN(path.dn_parts)
                        base = self.ldap.get(path.host, dn, attrsonly=True)
                        # Each attribute of the LDAP object is represented as a
                        # directory entry. A later getattr() call on these
                        # names will tell Fuse that these are files.
                        dir_entries.extend(base.names())

                        entries = self.ldap.search(path.host, dn, recur=False,
                                                attrsonly=True)
                        dir_entries.extend([name.DN.to_filename(entry.dn, str(dn))
                                           for entry in entries])
                    except InvalidDN:
                        LOG.debug('Invalid DN for fspath={}'.format(fspath))
                        return
                    except NoSuchObject:
                        LOG.debug('dn={} not found for fspath={}'
                                .format(dn, fspath))
                        return
                    except LdapException as ex:
                        LOG.error('Error reading dn={} for fspath={}. {}'
                                .format(dn, fspath, ex))
                        return

                    LOG.debug('DIRS={}  fspath={}'.format(self.dirs, fspath))
                    LOG.debug('dir_entries={}.  Extending with {}'
                            .format(dir_entries, self.dirs.get(fspath)))
                    dir_entries.extend(self.dirs.get(fspath, []))

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

    def mkdir(self, fspath, mode):
        path = name.Path(fspath, self.hosts)
        if path.len < 3:
            # No new directories in the host/base-dn directories
            return -errno.EPERM

        if not path.has_host_part():
            LOG.debug("path doesn't match any configured hosts: {}"
                      .format(fspath))
            return -errno.ENOENT

        if not path.has_base_dn_part():
            LOG.debug("path doesn't match any configured base DNs for host={} "
                      "path={}".format(path.host, fspath))
            return -errno.ENOENT

        # We don't have to check if the path already exists. Fuse will have
        # called getattr() and won't call mkdir() if the file/dir already
        # exists. However we don't want to create temporary (in-memory)
        # directories within other temporary directories, so we lookup the
        # parent here to ensure it exists in LDAP.

        parent_dn = name.DN.create_parent(path.dn_parts)
        try:
            if not parent_dn or not self.ldap.exists(path.host, parent_dn):
                return -errno.EINVAL
        except ldapcon.LdapException as ex:
            LOG.debug('Exception from ldap.exists for dn={} for fspath={}. {}'
                      .format(dn, fspath, ex))
            return -errno.EIO

        try:
            name.DN(path.dn_parts)
        except InvalidDN:
            LOG.debug('Invalid DN for fspath={}'.format(fspath))
            return -errno.EINVAL

        LOG.debug('DIRS={}  DIRPART={}  FILEPART={}'.format(self.dirs, path.dirpart, path.filepart))
        dirs = self.dirs.get(path.dirpart)
        if dirs:
            LOG.debug('APPEND FILEPART={} to DIRS FOR DIRPART={}'.format(path.filepart, path.dirpart))
            dirs.append(path.filepart)
        else:
            LOG.debug('SET FILEPART={} for DIRPART={}'.format(path.filepart, path.dirpart))
            self.dirs[path.dirpart] = [path.filepart]
        return 0

    def mknod(self, fspath, _1, _2):
        path = name.Path(fspath, self.hosts)
        if path.len < 3:
            # No files can be created in the host/base-dn directories
            return -errno.EPERM

        if not path.has_host_part():
            LOG.debug("path doesn't match any configured hosts: {}"
                      .format(fspath))
            return -errno.EPERM

        if not path.has_base_dn_part():
            LOG.debug("path doesn't match any configured base DNs for host={} "
                      "path={}".format(path.host, fspath))
            return -errno.EPERM

        if not path.filepart == ldapcon.Entry.ALL_ATTRIBUTES:
            # The only file we allow to be created is the all-attribute files
            LOG.debug('Only the all-attribute files ({}) can be created.'
                      .format(ldapcon.Entry.ALL_ATTRIBUTES))
            return -errno.EPERM

        # Must have a temporary/in-memory parent dir or a parent LDAP object
        if not self.dirs.get(path.dirpart):
            parent_dn = name.DN.create_parent(path.dn_parts)
            try:
                if not parent_dn or not self.ldap.exists(path.host, parent_dn):
                    return -errno.ENOENT
            except ldapcon.LdapException as ex:
                LOG.debug('Exception from ldap.exists for dn={} for fspath={}. {}'
                        .format(dn, fspath, ex))
                return -errno.EIO


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
