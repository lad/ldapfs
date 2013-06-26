
"""An API for LDAP connections and operations.

Multiple LDAP servers and base-dns are supported at once."""

import ldap
import logging

from .exceptions import LdapException, InvalidDN, NoSuchObject, NoSuchHost

LOG = logging.getLogger(__name__)


class Entry(object):
    """A thin wrapper for an LDAP Entry with conversion to/from strings."""

    ALL_ATTRIBUTES = '=attributes'

    def __init__(self, dn, attrs):
        self.dn = dn
        self.attrs = attrs

    def text(self, attr_name):
        """Return text representing the given attribute name.

        Attributes are represented as value,value,...
        A special name "=attributes" is used to denote all attributes where
        the return value is name=value,value,... for all attributes in the
        entry."""
        if attr_name == self.ALL_ATTRIBUTES:
            # Return name=value,value,... on separate lines for all attributes
            if self.attrs:
                retval = '\n'.join(['{}={}'.format(key, ','.join(vals))
                                    for key, vals in self.attrs.iteritems()]) \
                         + '\n'
            else:
                retval = ''
        else:
            vals = self.attrs.get(attr_name)
            if vals:
                # Return value,value, ...
                retval = ','.join(vals) + '\n'
            else:
                raise AttributeError()
        return retval

    def names(self):
        """Return the attribute names only."""
        return self.attrs.keys()

    def size(self, attr_name):
        """Return the size of text representation of the given attribute."""
        return len(self.text(attr_name))


class Connection(object):
    """An abstraction of an LDAP connection supporting multiple servers."""

    recur_to_scope = {False: ldap.SCOPE_ONELEVEL, True: ldap.SCOPE_SUBTREE}

    def __init__(self, hosts):
        self.hosts = hosts.copy()

    def open(self):
        """Connect to all configured LDAP hosts."""
        try:
            for host, values in self.hosts.iteritems():
                bind_uri = 'ldap://{}:{}'.format(host, values['port'])
                LOG.debug('Binding to uri={}'.format(bind_uri))
                con = ldap.initialize(bind_uri,
                                      trace_level=values['ldap_trace_level'])
                con.set_option(ldap.OPT_NETWORK_TIMEOUT, 2.0)
                con.simple_bind_s(values['bind_dn'], values['bind_password'])
                values['con'] = con
                LOG.debug('LDAP session established with host={}'.format(host))
        except ldap.INVALID_DN_SYNTAX as ex:
            raise InvalidDN(str(ex))
        except ldap.LDAPError as ex:
            raise LdapException('Error binding to {}: {}'.format(bind_uri, ex))

    def close(self):
        for host, values in self.hosts.iteritems():
            con = values.get('con')
            if con:
                try:
                    LOG.debug('Closing connection to {}'.format(host))
                    con.unbind()
                except ldap.LDAPError as ex:
                    LOG.debug('Error closing connection to {}: {}'
                              .format(host, ex))
                del values['con']

    def exists(self, host, dn):
        """Check if the given DN exists on the given server."""
        try:
            self._search(host, dn, ldap.SCOPE_BASE, True)
            return True
        except NoSuchObject:
            return False

    def get(self, host, dn, attrsonly=False):
        """Retrieve a single object at the given DN on the given server.

        Return a dictionary of attribute names/values"""
        return self._search(host, dn, ldap.SCOPE_BASE, attrsonly)[0]

    def getm(self, host, dn, attrsonly=False):
        """Retrieve multiple objects at the given DN on the given server.

        Return a list of dictionaries of attribute name/values."""
        return self._search(host, dn, ldap.SCOPE_BASE, attrsonly)

    def search(self, host, dn, recur=False, attrsonly=False):
        """Search for the LDAP objects at the given DN on the given server.

        Return a list of tuples, each one containing the DN of the LDAP
        object and a dictionary of its contents. The dictionary contains the
        attribute name/values of the object."""
        scope = self.recur_to_scope[bool(recur)]
        return self._search(host, dn, scope, attrsonly)

    def _search(self, host, dn, scope, attrsonly):
        """Internal search method to support public retrieval methods."""
        try:
            return [Entry(dn, attrs) for dn, attrs in
                    self.hosts[host]['con'].search_st(str(dn), scope,
                                                      attrsonly=attrsonly)]
        except KeyError:
            raise NoSuchHost('No configured LDAP host={}'.format(host))
        except ldap.INVALID_DN_SYNTAX:
            raise InvalidDN('Invalid DN={}'.format(dn))
        except ldap.NO_SUCH_OBJECT:
            raise NoSuchObject('No object found at host={} DN={}'
                               .format(host, dn))
