#!/usr/bin/env python

"""An LDAP backed file system using Fuse.

Usage: ldapfs.py -o config=<config-file-path> <mountpoint>

To unmount: fusermount -u <mountpoint>
"""

import sys
import errno
import fuse
import logging
import pprint

from .exceptions import LdapfsException, LdapException, InvalidDN, NoSuchObject, ConfigError
from .ldapconf import LdapConfigFile
from . import ldapcon
from . import name
from . import fs

LOG = logging.getLogger(__name__)
fuse.fuse_python_api = (0, 2)



class LdapFS(fuse.Fuse):
    """LDAP backed Fuse File System."""

    DEFAULT_CONFIG = '/etc/ldapfs/ldapfs.cfg'
    ATTRIBUTES_FILENAME = '.attributes'
    REQUIRED_BASE_CONFIG = ['log_file', 'log_format', 'log_levels', 'ldap_trace_level']
    PARSE_BASE_CONFIG = [('log_levels', LdapConfigFile.parse_log_levels),
                         ('ldap_trace_level', LdapConfigFile.parse_int)]
    REQUIRED_HOST_CONFIG = ['host', 'port', 'base_dns', 'bind_dn', 'bind_password']
    PARSE_HOST_CONFIG = [('port', LdapConfigFile.parse_int), ('base_dns', LdapConfigFile.validate_dns)]

    def __init__(self, *args, **kwargs):
        """Construct an LdapFS object absed on the Fuse class.

           :raises: ConfigError
        """
        fuse.Fuse.__init__(self, *args, **kwargs)
        self.flags = 0
        self.multithreaded = 0
        self.ldap = None

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

           :raises: ConfigError
        """
        config_parser = LdapConfigFile(self.config)

        # We should have an 'ldapfs' section common to the entire app, and
        # separate sections for each LDAP host that we are to connect to.
        config_sections = config_parser.get_sections()
        try:
            config_sections.remove('ldapfs')
        except ValueError:
            raise ConfigError('No "ldapfs" section found in config file. Path={}'.format(self.config))

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

        self.ldap = ldapcon.Connection(self.hosts)

        LOG.debug('ldapfs-config={}'.format(pprint.pformat(config_items)))
        LOG.debug('hosts-config={}'.format(pprint.pformat(self.hosts)))

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

    def getattr(self, fspath):
        """Return stat structure for the given path."""
        LOG.debug('ENTER: fspath={}'.format(fspath))
        path = name.Path(fspath, self.hosts)
        if not path:
            LOG.debug('Empty path')
            return -errno.ENOENT
        elif path.is_root_path():
            LOG.debug('Root path')
            return fs.Stat(isdir=True)

        if not path.has_host_part():
            LOG.debug("path doesn't match any configured hosts: {}".format(fspath))
            return -errno.ENOENT

        if path.len == 1:
            # No more path components to look at - we're done
            return fs.Stat(isdir=True)

        if not path.has_base_dn_part():
            LOG.debug("path doesn't match any configured base DNs for host={} path={}".format(path.host, fspath))
            return -errno.ENOENT

        # Now we need to find an object that matches the remaining path (without the
        # leading host and base-dn)

        dn = name.DN.create(path.dn_parts)
        try:
            if dn and self.ldap.exists(path.host, dn):
                # We found a matching LDAP object. We're done.
                return fs.Stat(isdir=True)
        except ldapcon.LdapException as ex:
            #LOG.debug('dn={}. Exception={}'.format(dn, ex))
            LOG.debug('fspath={} Exception={}'.format(fspath, ex))
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

            entry = self.ldap.get(path.host, parent_dn)[0][1]
        except ldapcon.NoSuchObject:
            LOG.debug('parent_dn={} not found'.format(parent_dn))
            return -errno.ENOENT
        except ldapcon.LdapException as ex:
            LOG.debug('parent_dn={}. Exception={}'.format(parent_dn, ex))
            return -errno.ENOENT

        # Check if the filename part matches the special file ".attributes"
        if path.filepart == self.ATTRIBUTES_FILENAME:
            LOG.debug('Return {}'.format(self.ATTRIBUTES_FILENAME))
            return fs.Stat(isdir=False, size=fs.entry_size(entry))
        else:
            # We have the parent object. Check if there's an attribute with the
            # same name as the input filename
            attr = entry.get(path.filepart)
            if attr:
                LOG.debug('PARENT-ENTRY={}'.format(entry))
                return fs.Stat(isdir=False, size=fs.attr_size(attr))
            else:
                LOG.debug('Attribute={} not found in parent-dn={} for fspath={}'.format(
                          path.filepart, parent_dn, fspath))
                return -errno.ENOENT

    def readdir(self, fspath, offset):
        """Read the given directory path and yield its contents."""
        LOG.debug('ENTER: fspath={} offset={}'.format(fspath, offset))
        dir_entries = ['.', '..']

        path = name.Path(fspath, self.hosts)
        if not path:
            return
        elif path.is_root_path():
            LOG.debug('Root path')
            dir_entries.extend(self.hosts.keys())
        else:
            if not path.has_host_part():
                LOG.debug("path doesn't match any configured hosts: {}".format(fspath))
                return

            if path.len == 1:
                # root dir has a list of the base dns
                dir_entries.extend(self.hosts[path.host]['base_dns'])
            else:
                if not path.has_base_dn_part():
                    LOG.debug("path doesn't match any configured base DNs for host={} path={}".format(
                              path.host, fspath))
                    return

                # Each dir has a .attributes file that contains all attributes
                # for that LDAP object that the current dir is representing
                dir_entries.append(self.ATTRIBUTES_FILENAME)

                try:
                    dn = name.DN(path.dn_parts)
                    base = self.ldap.get(path.host, dn, attrsonly=True)[0][1]
                    # Each attribute of the LDAP object is represented as a directory
                    # entry. A later getattr() call on these names will tell Fuse that
                    # these are files.
                    dir_entries.extend(base.keys())

                    entries = self.ldap.search(path.host, dn, recur=False, attrsonly=True)
                    dir_entries.extend([name.DN.to_filename(entry[0], str(dn)) for entry in entries])
                except InvalidDN:
                    LOG.debug('Invalid DN for fspath={}'.format(fspath))
                    return
                except LdapException as ex:
                    LOG.error('Error reading dn={} for fspath={}. {}'.format(dn, fspath, ex))
                    return

        for ent in dir_entries:
            LOG.debug('yield {}'.format(ent))
            yield fuse.Direntry(ent)

    # pylint: disable-msg=R0201
    def mknod(self, fspath, mode, dev):
        """Create a file entry at the given path with the given mode."""
        LOG.debug('ENTER: fspath={} mode={} dev={}'.format(fspath, mode, dev))
        return 0

    # pylint: disable-msg=R0201
    def unlink(self, fspath):
        """Remove the file entry at the given path."""
        LOG.debug('ENTER: fspath={}'.format(fspath))
        return 0

    def read(self, fspath, size, offset):
        """Read the file entry at the given path, size and offset."""
        LOG.debug('ENTER: fspath={} size={} offset={}'.format(fspath, size, offset))

        path = name.Path(fspath, self.hosts)
        if path.len < 3:
            # There are no files in the first two directories (host/base-dn)
            return -errno.ENOENT

        if not path.has_host_part():
            LOG.debug("path doesn't match any configured hosts: {}".format(fspath))
            return

        if not path.has_base_dn_part():
            LOG.debug("path doesn't match any configured base DNs for host={} path={}".format(
                        path.host, fspath))
            return -errno.ENOENT

        try:
            # Look for an LDAP object matching the directory name
            dn = name.DN.create_parent(path.dn_parts)
            entry = self.ldap.get(path.host, dn)[0][1]
            LOG.debug('Entry={}'.format(entry))
        except InvalidDN:
            LOG.debug('Invalid dn from fspath={}'.format(fspath))
            return -errno.ENOENT
        except (NoSuchObject, InvalidDN):
            LOG.debug('dn={} not found for fspath={}'.format(dn, fspath))
            return -errno.ENOENT
        except LdapException as ex:
            LOG.debug('dn={}. fspath={}. Exception={}'.format(dn, fspath, ex))
            return -errno.ENOENT

        LOG.debug('entry={}'.format(entry))

        if path.filepart == self.ATTRIBUTES_FILENAME:
            # Return name=value on separate lines for all attributes
            retval = '\n'.join(['{}={}'.format(key, ','.join(val)) for key, val in entry.iteritems()]) + '\n'
        else:
            attr = entry.get(path.filepart)
            if attr:
                retval = ','.join(attr) + '\n'
            else:
                LOG.debug('Attribute={} not found in dn={} for fspath={}'.format(path.filepart, dn, fspath))
                return -errno.ENOENT

        return retval[offset:size]

    def write(self, fspath, buf, offset):
        """Write to given buffer at the given path at the given offset."""
        LOG.debug('ENTER: fspath={} buf={} offset={}'.format(fspath, buf, offset))
        return 0

    # pylint: disable-msg=R0201
    def open(self, fspath, flags):
        """Open a file entry at the given path with the given flags."""
        LOG.debug('ENTER: fspath={} flags={}'.format(fspath, flags))
        return 0

    # pylint: disable-msg=R0201
    def release(self, fspath, flags):
        """Close a file entry at the given path with the given flags."""
        LOG.debug('ENTER: fspath={} flags={}'.format(fspath, flags))
        return 0

    # pylint: disable-msg=R0201
    def truncate(self, fspath, size):
        """Truncate the file entry at the given path to the given size."""
        LOG.debug('ENTER: fspath={} size={}'.format(fspath, size))
        return 0

    # pylint: disable-msg=R0201
    def utime(self, fspath, times):
        """Set the time of the entry at the given path."""
        LOG.debug('ENTER: fspath={} times={}'.format(fspath, times))
        return 0

    # pylint: disable-msg=R0201
    def mkdir(self, fspath, mode):
        """Create a directory entry at the given path with the given mode."""
        LOG.debug('ENTER: fspath={} mode={}'.format(fspath, mode))
        return 0

    # pylint: disable-msg=R0201
    def rmdir(self, fspath):
        """Remove a directory entry at the given path."""
        LOG.debug('ENTER: fspath={}'.format(fspath))
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
            #src_dn = name.path2dn(src)
            #dst_rdn = name.path2rdn(dst)
            #LOG.debug('rename_s({}, {})'.format(src_dn, dst_rdn))
            #con = self.hosts[('localhost', 'dc=dunne,dc=ie')]['con']
            #con.rename_s(src_dn, dst_rdn)
        #except InvalidDN:
            #if not src_dn:
                #LOG.debug('Invalid dn from src path={}'.format(src))
            #else:
                #LOG.debug('Invalid rdn from dst path={}'.format(dst))
            #return -errno.EINVAL
        #except LdapException as ex:
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
        except (LdapfsException, fuse.FuseError) as main_ex:
            LOG.error(str(main_ex))
            print main_ex


if __name__ == '__main__':
    LdapFS.run()
