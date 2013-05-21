
"""All LdapFS exceptions are defined here."""

class LdapfsException(Exception):
    """Base class for all LdapFS exceptions."""
    pass


class LdapException(LdapfsException):
    """Base class for LDAP related exceptions."""
    pass


class InvalidDN(LdapException):
    """The given DN is invalid."""
    pass


class NoSuchObject(LdapException):
    """The requested LDAP object does not exist."""
    pass


class NoSuchHost(LdapException):
    """No host configured for the gievn host name."""
    pass


class ConfigError(LdapException):
    """Config parsing, formating or absence errors."""
    pass


