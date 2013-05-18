
class LdapfsException(Exception):
    pass


class LdapException(LdapfsException):
    pass


class InvalidDN(LdapException):
    pass


class NoSuchObject(LdapException):
    pass


class NoSuchHost(LdapException):
    pass


class ConfigError(LdapException):
    """Config parsing, formating or absence errors."""
    pass


