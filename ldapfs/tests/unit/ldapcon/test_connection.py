
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
    mocks = mock.Mock()
    mocks.entry = mock.Mock()
    mocks.ldap = mock.Mock()
    mocks.con = mock.Mock()
    mocks.ldap.initialize.return_value = mocks.con

    def patch(monkeypatch):
        monkeypatch.setattr(ldapfs.ldapcon, 'ldap', mocks.ldap)
        monkeypatch.setattr(ldapfs.ldapcon, 'Entry', mocks.entry)

    mocks.patch = patch
    return [mocks]


def funcarg_init_hosts():
    return [({'host': ['values']}),
            ({'h1': (1, 2), 'h2': (3, 4)})]


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


def funcarg_open_args():
    hosts = {'host1': {'port': 389,
                       'ldap_trace_level': 0,
                       'bind_password': 'pass1',
                       'bind_dn': 'cn=binddn1',
                       'base_dns': ['dc=ie', 'cn=cn1,dc=ie']},
             'host2': {'port': 636,
                       'ldap_trace_level': 1,
                       'bind_password': 'pass2',
                       'bind_dn': 'cn=binddn2',
                       'base_dns': ['dc=ie', 'cn=cn2,dc=ie']},
             'host3.domain.com': {'port': 12345,
                                  'ldap_trace_level': 2,
                                  'bind_password': 'pass3',
                                  'bind_dn': 'cn=binddn3',
                                  'base_dns': ['dc=ie', 'cn=cn3,dc=ie']}}
    init_args = [['ldap://host1:389'],
                 ['ldap://host2:636'],
                 ['ldap://host3.domain.com:12345']]
    init_kwargs = [{'trace_level': 0},
                   {'trace_level': 1},
                   {'trace_level': 2}]
    bind_args = [['cn=binddn1', 'pass1'],
                 ['cn=binddn2', 'pass2'],
                 ['cn=binddn3', 'pass3']]

    return [(hosts, init_args, init_kwargs, bind_args)]


def test_open(monkeypatch, open_args, mocks):
    hosts, init_args_list, init_kwargs_list, bind_args_list = open_args
    con = ldapfs.ldapcon.Connection(hosts)

    mocks.patch(monkeypatch)
    con.open()

    expected_call_count = len(init_args_list)

    assert mocks.ldap.initialize.call_count == expected_call_count
    assert mocks.con.simple_bind_s.call_count == expected_call_count

    for init_args, init_kwargs, bind_args in \
        zip(init_args_list, init_kwargs_list, bind_args_list):
        mocks.ldap.initialize.assert_any_call(*init_args, **init_kwargs)
        mocks.con.simple_bind_s.assert_any_call(*bind_args)


def test__search(monkeypatch, mocks):
    hosts = {'host': {'port': 389, 'ldap_trace_level': 0,
                      'bind_password': 'pass', 'bind_dn': 'bdn',
                      'base_dns': ['dc=ie', 'cn=cn1,dc=ie']}}
    host = 'host'
    dn = mock.MagicMock()
    dn.__str__.return_value = 'cn1,dc=ie'
    attrs = {'attr1': 'value1', 'attr2': 'value2'}
    search_return_value = [(dn, attrs)]
    scope = 0
    attrsonly = False

    mocks.con.search_st.return_value = search_return_value
    mocks.patch(monkeypatch)

    con = ldapfs.ldapcon.Connection(hosts)
    con.open()

    mocks.entry.reset_mock()

    result = con._search(host, dn, scope, attrsonly)
    assert mocks.entry.call_count == len(search_return_value)
    for dn, attrs in search_return_value:
        mocks.entry.assert_called_with(dn, attrs)
