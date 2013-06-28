
import pytest
import mock
import ldapfs.ldapcon


def pytest_generate_tests(metafunc):
    # pytest has various ways to parametrize tests. Here I've used one global
    # function per argument. The function is expected to return a list of
    # values. The test function will be run once for each value.
    for argname in metafunc.funcargnames:
        fn = globals().get('funcarg_{}'.format(argname))
        if fn:
            argvalues = globals()['funcarg_{}'.format(argname)]()
            metafunc.parametrize(argname, argvalues)


def funcarg_mocks():
    """Return mocks for all ldapcon dependencies"""
    class INVALID_DN_SYNTAX(Exception): pass
    class LDAPError(Exception): pass

    mocks = mock.Mock()
    mocks.entry = mock.Mock()
    mocks.ldap = mock.Mock()
    mocks.con = mock.Mock()
    mocks.ldap.initialize.return_value = mocks.con

    mocks.ldap.INVALID_DN_SYNTAX = INVALID_DN_SYNTAX
    mocks.ldap.LDAPError = LDAPError

    def patch(monkeypatch, ldap=mocks.ldap, entry=mocks.entry):
        monkeypatch.setattr(ldapfs.ldapcon, 'ldap', ldap)
        monkeypatch.setattr(ldapfs.ldapcon, 'Entry', entry)

    mocks.patch = patch
    return [mocks]


def funcarg_init_hosts():
    return [({'host': ['values']}),
            ({'h1': (1, 2), 'h2': (3, 4)})]


def make_three_hosts():
    h1 = {'host1': {'port': 389,
                    'ldap_trace_level': 0,
                    'bind_password': 'pass1',
                    'bind_dn': 'cn=binddn1',
                    'base_dns': ['dc=ie', 'cn=cn1,dc=ie']}}
    h2 = {'host2': {'port': 636,
                    'ldap_trace_level': 1,
                    'bind_password': 'pass2',
                    'bind_dn': 'cn=binddn2',
                    'base_dns': ['dc=ie', 'cn=cn2,dc=ie']}}
    h3 = {'host3.domain.com': {'port': 12345,
                               'ldap_trace_level': 2,
                               'bind_password': 'pass3',
                               'bind_dn': 'cn=binddn3',
                               'base_dns': ['dc=ie', 'cn=cn3,dc=ie']}}

    hosts1 = dict(**h1)

    hosts2 = dict(**h1)
    hosts2.update(**h2)

    hosts3 = dict(**h1)
    hosts3.update(**h2)
    hosts3.update(**h3)
    return hosts1, hosts2, hosts3


def funcarg_open_args():
    hosts1, hosts2, hosts3 = make_three_hosts()
    init_args = [['ldap://host1:389'],
                 ['ldap://host2:636'],
                 ['ldap://host3.domain.com:12345']]
    init_kwargs = [{'trace_level': 0},
                   {'trace_level': 1},
                   {'trace_level': 2}]
    bind_args = [['cn=binddn1', 'pass1'],
                 ['cn=binddn2', 'pass2'],
                 ['cn=binddn3', 'pass3']]

    return [(hosts1, init_args[:1], init_kwargs[:1], bind_args[:1]),
            (hosts2, init_args[:2], init_kwargs[:2], bind_args[:2]),
            (hosts3, init_args, init_kwargs, bind_args)]


def funcarg_search_args():
    hosts1, hosts2, hosts3 = make_three_hosts()

    dn1 = mock.MagicMock()
    dn1.__str__.return_value = 'cn1,dc=ie'
    attrs = {'attr{}'.format(i): 'value{}'.format(i) for i in range(10)}
    search_return_value = [(dn1, attrs)]

    return [(hosts1, dn1, attrs, search_return_value),
            (hosts2, dn1, attrs, search_return_value),
            (hosts3, dn1, attrs, search_return_value)]



def test_init_hosts(monkeypatch, init_hosts, mocks):
    mocks.patch(monkeypatch)
    con = ldapfs.ldapcon.Connection(init_hosts)
    assert con.hosts == init_hosts


def test_init_hosts_copy(monkeypatch, init_hosts, mocks):
    mocks.patch(monkeypatch)
    con = ldapfs.ldapcon.Connection(init_hosts)
    copy_hosts = init_hosts.copy()
    k = init_hosts.keys()[0]
    del init_hosts[k]
    assert con.hosts == copy_hosts


def test_open(monkeypatch, open_args, mocks):
    hosts, init_args_list, init_kwargs_list, bind_args_list = open_args
    con = ldapfs.ldapcon.Connection(hosts)

    mocks.ldap.initialize.reset_mock()
    mocks.con.simple_bind_s.reset_mock()
    mocks.patch(monkeypatch)
    con.open()

    expected_call_count = len(init_args_list)

    assert mocks.ldap.initialize.call_count == expected_call_count
    assert mocks.con.simple_bind_s.call_count == expected_call_count

    for init_args, init_kwargs, bind_args in \
        zip(init_args_list, init_kwargs_list, bind_args_list):
        mocks.ldap.initialize.assert_any_call(*init_args, **init_kwargs)
        mocks.con.simple_bind_s.assert_any_call(*bind_args)


def test_open_invalid_dn(monkeypatch, open_args, mocks):
    hosts, init_args_list, init_kwargs_list, bind_args_list = open_args
    mocks.ldap.initialize.side_effect = mocks.ldap.INVALID_DN_SYNTAX('...')
    mocks.patch(monkeypatch)
    con = ldapfs.ldapcon.Connection(hosts)

    with pytest.raises(ldapfs.exceptions.InvalidDN):
        con.open()


def test_open_ldap_error(monkeypatch, open_args, mocks):
    hosts, init_args_list, init_kwargs_list, bind_args_list = open_args
    mocks.ldap.initialize.side_effect = mocks.ldap.LDAPError('...')
    mocks.patch(monkeypatch)
    con = ldapfs.ldapcon.Connection(hosts)

    with pytest.raises(ldapfs.exceptions.LdapException):
        con.open()


def test_close(monkeypatch, open_args, mocks):
    hosts, _, _, _ = open_args
    mocks.con.unbind.reset_mock()
    mocks.patch(monkeypatch)
    con = ldapfs.ldapcon.Connection(hosts)
    con.open()

    con.close()
    expected_call_count = len(hosts)
    assert mocks.con.unbind.call_count == expected_call_count


def test_close_ldap_error(monkeypatch, open_args, mocks):
    hosts, _, _, _ = open_args
    mocks.con.unbind.reset_mock()
    mocks.con.unbind.side_effect = mocks.ldap.LDAPError('...')
    mocks.patch(monkeypatch)
    con = ldapfs.ldapcon.Connection(hosts)
    con.open()

    con.close()
    expected_call_count = len(hosts)
    assert mocks.con.unbind.call_count == expected_call_count


def test__search(monkeypatch, search_args, mocks):
    hosts, dn1, attrs, search_return_value = search_args
    scope = 0
    attrsonly = False

    mocks.con.search_st.return_value = search_return_value
    mocks.patch(monkeypatch)

    con = ldapfs.ldapcon.Connection(hosts)
    con.open()
    mocks.entry.reset_mock()

    result = con._search(hosts.keys()[0], dn1, scope, attrsonly)
    assert mocks.entry.call_count == len(search_return_value)
    for dn, attrs in search_return_value:
        mocks.entry.assert_called_with(dn, attrs)
