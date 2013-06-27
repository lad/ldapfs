
import pytest
from ldapfs.ldapcon import Entry


def pytest_generate_tests(metafunc):
    # pytest has various ways to parametrize tests. Here I've used one global
    # function per argument. The function is expected to return a list of
    # values. The test function will be run once for each value.
    for argname in metafunc.funcargnames:
        argvalues = globals()['{}'.format(argname)]()
        metafunc.parametrize(argname, argvalues)


def init_dn():
    return ['', 'dn']

def test_init_dn(init_dn):
    entry = Entry(init_dn, [])
    assert entry.dn == init_dn


def init_attrs():
    return [[], ['a'], ['a', 'b', 'c'], [('a', 1), ('b', 2)]]

def test_init_attrs(init_attrs):
    entry = Entry('dn', init_attrs)
    assert entry.attrs == init_attrs


def eq_entry():
    entries = [Entry('dn1', ['attr1', 'attr2']),
               Entry('dn2', ['a']),
               Entry('dn3', [])]
    return zip(entries, entries)

def test_eq_entry(eq_entry):
    entry, eq = eq_entry
    assert entry == eq


def eq_str():
    strs = ['dn1', 'dn2', 'dn3']
    return zip(strs, strs)

def test_eq_str(eq_str):
    entry, eq = eq_str
    assert entry == eq


def neq_entry():
    entries1 = [Entry('dn1', ['attr1', 'attr2']),
                Entry('dn2', ['a']),
                Entry('dn3', [])]
    entries2 = [Entry('ndn1', ['attr1', 'attr2']),
                Entry('ndn2', ['a']),
                Entry('ndn3', [])]
    return zip(entries1, entries2)

def test_neq_entry(neq_entry):
    entry, neq = neq_entry
    assert entry != neq


def neq_str():
    strs1 = ['dn1', 'dn2', 'dn3']
    strs2 = ['xn1', 'xn2', 'xn3']
    return zip(strs1, strs2)

def test_neq_str(neq_str):
    entry, neq = neq_str
    assert entry != neq


def text_args():
    entry1 = Entry('dn', {'a': ['1', '2'], 'b': ['3']})
    entry2 = Entry('dn', {})
    return [(entry1, 'a', '1,2\n'),
            (entry1, Entry.ALL_ATTRIBUTES, 'a=1,2\nb=3\n'),
            (entry2, Entry.ALL_ATTRIBUTES, '')]

def test_text(text_args):
    entry, attr_name, expected = text_args
    assert entry.text(attr_name) == expected


def test_text_error(text_args):
    entry, attr_name, __ = text_args
    with pytest.raises(AttributeError):
        entry.text(attr_name + '-xxx')


def names_args():
    entry1 = Entry('dn1', {'a': ['1'], 'b': ['3'], 'ckey': ['4', '5', '6']})
    entry2 = Entry('dn2', {'a': ['1']})
    entry3 = Entry('dn3', {})
    return [(entry1, ['a', 'b', 'ckey']),
            (entry2, ['a']),
            (entry3, [])]

def test_names(names_args):
    entry, expected = names_args
    assert entry.names() == expected


def size_args():
    entry1 = Entry('dn1', {'a': ['1'], 'b': ['3'], 'ckey': ['4', '5', '6']})
    entry2 = Entry('dn2', {'a': ['1']})
    entry3 = Entry('dn3', {})
    return [(entry1, 'b', 2),
            (entry1, 'ckey', 6),
            (entry1, Entry.ALL_ATTRIBUTES, 19),
            (entry2, 'a', 2),
            (entry2, Entry.ALL_ATTRIBUTES, 4),
            (entry3, Entry.ALL_ATTRIBUTES, 0)]

def test_size(size_args):
    entry, attr_name, expected = size_args
    assert entry.size(attr_name) == expected
