
"""An API for LDAP connections and operations.

Multiple LDAP servers and base-dns are supported at once."""

import ldap
import logging
from .exceptions import LdapException, InvalidDN, NoSuchObject, NoSuchHost

LOG = logging.getLogger(__name__)


class Connection(object):
    """An abstraction of an LDAP connection supporting multiple servers."""

    recur_to_scope = {False: ldap.SCOPE_ONELEVEL, True: ldap.SCOPE_SUBTREE}

    def __init__(self, hosts, ldap_trace_level=0):
        self.hosts = hosts.copy()
        self.ldap_trace_level = ldap_trace_level

    def connect(self):
        """Connect to all configured LDAP hosts."""
        try:
            for host, values in self.hosts.iteritems():
                bind_uri = 'ldap://{}:{}'.format(host, values['port'])
                LOG.debug('Binding to uri={}'.format(bind_uri))
                con = ldap.initialize(bind_uri,
                                      trace_level=self.ldap_trace_level)
                con.set_option(ldap.OPT_NETWORK_TIMEOUT, 2.0)
                con.simple_bind_s(values['bind_dn'], values['bind_password'])
                values['con'] = con
                LOG.debug('LDAP session established with host={}'.format(host))
        except ldap.INVALID_DN_SYNTAX as ex:
            raise InvalidDN(str(ex))
        except ldap.LDAPError as ex:
            raise LdapException('Error binding to {}: {}'.format(bind_uri, ex))

    def exists(self, host, dn):
        """Check if the given DN exists on the given server."""
        LOG.debug('ENTER: host={} dn={}'.format(host, dn))
        try:
            self._search(host, dn, ldap.SCOPE_BASE, True)
            return True
        except NoSuchObject:
            return False

    def get(self, host, dn, attrsonly=False):
        """Retrieve the LDAP obejct at the given DN on the given server."""
        LOG.debug('ENTER: host={} dn={} attrsonly={}'
                  .format(host, dn, attrsonly))
        return self._search(host, dn, ldap.SCOPE_BASE, attrsonly)


    def search(self, host, dn, recur=False, attrsonly=False):
        """Search for the LDAP obejcts at the given DN on the given server."""
        LOG.debug('ENTER: host={} dn={} recur={} attrsonly={}'
                  .format(host, dn, recur, attrsonly))
        scope = self.recur_to_scope.get(bool(recur))
        return self._search(host, dn, scope, attrsonly)

    def _search(self, host, dn, scope, attrsonly):
        """Internal search method to support public retrieval methods."""
        try:
            return self.hosts[host]['con'].search_st(str(dn), scope,
                                                     attrsonly=attrsonly)
        except KeyError:
            raise NoSuchHost('No configured LDAP host={}'.format(host))
        except ldap.INVALID_DN_SYNTAX:
            raise InvalidDN('Invalid DN={}'.format(dn))
        except ldap.NO_SUCH_OBJECT:
            raise NoSuchObject('No object found at host={} DN={}'
                               .format(host, dn))
