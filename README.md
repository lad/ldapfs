
LdapFS
======

An LDAP backed file system.

This is a small Fuse based file system written using fuse-python and
python-ldap. It allows you to mount an LDAP hierarchy as a set of
files and directories on disk. It is most useful for examing an existing
hierarchy.

**I use this solely for development purposes. It has never been used in
production**

A brief overview:

* Multiple LDAP servers with multiple base DNs can be mounted under one mountpoint.

* LDAP objects are represented as directories with child objects as sub-directories.

* Object attributes are represented as files within their object's directory.

* The name of an attribute file is the same as the attribute name

* The contents of the file is a single line, starting with the attribute name,
  followed by an "=" character, followed by the attribute value, ending with a
  "\n" character attribute.

* The size of an attribute file reported to the file system includes size for
  the "=" and "\n" characters in addition to the name and value pair.

* Each directory contains a special ".attributes" file. The file contains one
  line for each attribute of that directory's LDAP object. The format of
  each line is the same as the attribute file.

Installation
------------

The package is not yet on pypi. To install clone this repository and install
with the following:

  # git clone git://github.com/lad/ldapfs.git
  # cd ldapfs
  # python setup.py install


Setup
-----

The configuration file in <install-dir>/etc/ldapfs.cfg is used to specify the
LDAP servers, credentials and base DNs to mount.

    [ldapfs]
    log_file = /var/log//ldapfs.log
    # Uncomment to log to stdout
    # log_file = -
    log_format = %%(funcName)s() - %%(message)s
    log_levels = root:error, ldapfs:error
    ldap_trace_level = 0

    [LDAP Server 1]
    host = opendj.example.com
    port = 389
    bind_dn = cn=Directory Manager
    bind_password = password
    # The base DNs should be each be listed within double-quotes (") and be separated by one or more spaces
    base_dns = "dc=dell,dc=com" "cn=schema" "cn=monitor" "cn=config" "cn=backups" "cn=admin data" "cn=tasks" "cn=ads-truststore"

    [LDAP Server 2]
    host = openldap.example.com
    port = 389
    bind_dn = cn=admin,dc=dunne,dc=ie
    bind_password = password
    base_dns = "dc=dunne,dc=ie"
