
"""LDAP Config File Support."""

from .conf import ConfigError, ConfigFile
import ldap


class LdapConfigFile(ConfigFile):
    """Ldapfs oriented wrapper for ConfigFile."""

    @staticmethod
    def validate_dns(dns):
        """Validate and format DNs from config."""
        dns = [dn for dn in dns.split('"') if dn.strip()]
        if not dns:
            raise ConfigError('Empty DN configuration.')
        for dn in dns:
            try:
                ldap.dn.explode_dn(dn)
            except ldap.DECODING_ERROR:
                raise ConfigError('Invalid DN "{}".'.format(dn))
        return dns
