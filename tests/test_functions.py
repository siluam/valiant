from os import environ
from parametrized import parametrized
from pytest import fixture, mark
from tempfile import TemporaryFile
from valiant.miscellaneous import (
    any_in,
    all_in,
    conf_to_dict,
    configure,
    configuring,
    dict_to_conf,
    environment,
    escapeDoubleQuotes,
    escapeQuotes,
    escapeQuotesJoinMapString,
    escapeSingleQuotes,
    format_conf,
    getFuncDefaults,
    is_coll,
    module_installed,
    normalizeMultiline,
    toColl,
    update,
    updateWithStrings,
)


@mark.anyAllIn
class TestAnyAllIn:
    def test_all(self):
        assert all_in(range(10), 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)

    def test_any(self):
        assert any_in(range(10), 0, 2, 4, 6, 8, 10, 12, 14, 16, 18)

    def test_not_all(self):
        assert not all_in(range(10), 0, 2, 4, 6, 8, 10, 12, 14, 16, 18)

    def test_not_any(self):
        assert not any_in(range(10), 10, 11, 12, 13, 14, 15, 16, 17, 18, 19)

    def test_not_in_all(self):
        assert all_in(range(10), 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, not_in=True)

    def test_not_in_any(self):
        assert any_in(range(10), 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, not_in=True)

    @parametrized
    @mark.xfail(raises=TypeError)
    def test_none(self, func=(any_in, all_in)):
        assert func()


@mark.getFuncDefaults
class TestGetFuncDefaults:
    def func(self, a, b=None):
        pass

    def test_args(self):
        assert getFuncDefaults(self.func).defaults.b is None


@mark.toColl
@mark.order(0)
@parametrized.zip
def test_toColl(func=(list, set, tuple, dict), output=([0], {0}, (0,), {0: None})):
    assert toColl(0, func) == output


@mark.module_installed
@parametrized
def test_module_installed(resources, ext=("py", "bzl")):
    assert module_installed(resources / f"valiant.{ext}", ext).dirs == ["./."]


@mark.conf
class TestConfDict:
    @fixture
    def dct1(self):
        return dict(a="0", b="1")

    @fixture
    def dct2(self):
        return dict(c="true", d="false")

    @fixture
    def dct3(self):
        return dict(a_b="ab", cd="c = d")

    @fixture
    def dct(self, dct1, dct2, dct3):
        return {**dct1, **dct2, **dct3}

    @fixture
    def conf1(self):
        return "a=0\nb= 1"

    @fixture
    def conf2(self):
        return "c =true\nd = false"

    @fixture
    def conf3(self):
        return "a-b=ab\ncd = c = d"

    @fixture
    def conf(self, conf1, conf2, conf3):
        return "\n".join((conf1, conf2, conf3))

    @fixture
    def fconf(self, conf):
        return format_conf(conf)

    def test_conf_to_dict(self, conf, dct):
        assert conf_to_dict(conf) == dct

    def test_dict_to_original_conf(self, conf, dct):
        assert dict_to_conf(**dct) != conf

    def test_dict_to_formatted_conf(self, fconf, dct):
        assert dict_to_conf(**dct) == fconf


@mark.configure
@mark.usefixtures(
    "conf1", "conf2", "conf3", "conf", "fconf", "dct1", "dct2", "dct3", "dct"
)
class TestConfigure(TestConfDict):
    @fixture
    def config(self):
        return environ.get("NIX_CONFIG", "").strip()

    def test_replace_conf(self, conf, fconf, config):
        try:
            configure(_replace=True, _config=conf)
            assert environ["NIX_CONFIG"] == fconf
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_replace_dict(self, fconf, dct, config):
        try:
            configure(_replace=True, **dct)
            assert environ["NIX_CONFIG"] == fconf
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_replace_file(self, conf, fconf, config):
        try:
            with TemporaryFile("w+") as file:
                file.write(conf)
                file.seek(0)
                configure(_replace=True, _file=file)
                assert environ["NIX_CONFIG"] == fconf
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_replace_multiple(self, conf1, conf2, fconf, dct3, config):
        try:
            with TemporaryFile("w+") as file:
                file.write(conf2)
                file.seek(0)
                configure(_replace=True, _config=conf1, _file=file, **dct3)
                assert environ["NIX_CONFIG"] == fconf
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_append_conf(self, conf, fconf, config):
        try:
            configure(_config=conf)
            assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_append_dict(self, fconf, config, dct):
        try:
            configure(**dct)
            assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_append_file(self, conf, fconf, config):
        try:
            with TemporaryFile("w+") as file:
                file.write(conf)
                file.seek(0)
                configure(_file=file)
                assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config

    def test_append_multiple(self, conf1, conf2, fconf, dct3, config):
        try:
            with TemporaryFile("w+") as file:
                file.write(conf2)
                file.seek(0)
                configure(_config=conf1, _file=file, **dct3)
                assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        finally:
            environ["NIX_CONFIG"] = config
            assert environ["NIX_CONFIG"] == config


@mark.configure
@mark.configuring
@mark.usefixtures(
    "conf1", "conf2", "conf3", "conf", "fconf", "dct1", "dct2", "dct3", "dct", "config"
)
class TestConfiguring(TestConfigure):
    def test_replace_conf(self, conf, fconf, config):
        with configuring(_replace=True, _config=conf):
            assert environ["NIX_CONFIG"] == fconf
        assert environ["NIX_CONFIG"] == config

    def test_replace_dict(self, fconf, dct, config):
        with configuring(_replace=True, **dct):
            assert environ["NIX_CONFIG"] == fconf
        assert environ["NIX_CONFIG"] == config

    def test_replace_file(self, conf, fconf, config):
        with TemporaryFile("w+") as file:
            file.write(conf)
            file.seek(0)
            print(file.read())
            file.seek(0)
            with configuring(_replace=True, _file=file):
                assert environ["NIX_CONFIG"] == fconf
        assert environ["NIX_CONFIG"] == config

    def test_replace_multiple(self, conf1, conf2, fconf, dct3, config):
        with TemporaryFile("w+") as file:
            file.write(conf2)
            file.seek(0)
            with configuring(_replace=True, _config=conf1, _file=file, **dct3):
                assert environ["NIX_CONFIG"] == fconf
        assert environ["NIX_CONFIG"] == config

    def test_append_conf(self, conf, fconf, config):
        with configuring(_config=conf):
            assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        assert environ["NIX_CONFIG"] == config

    def test_append_dict(self, fconf, dct, config):
        with configuring(**dct):
            assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        assert environ["NIX_CONFIG"] == config

    def test_append_file(self, conf, fconf, config):
        with TemporaryFile("w+") as file:
            file.write(conf)
            file.seek(0)
            with configuring(_file=file):
                assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        assert environ["NIX_CONFIG"] == config

    def test_append_multiple(self, conf1, conf2, fconf, dct3, config):
        with TemporaryFile("w+") as file:
            file.write(conf2)
            file.seek(0)
            with configuring(_config=conf1, _file=file, **dct3):
                assert environ["NIX_CONFIG"] == (config + "\n" + fconf)
        assert environ["NIX_CONFIG"] == config


@mark.is_coll
class TestIsColl:
    def test_true(self):
        def yield_():
            for i in range(0):
                yield i

        def yield_from():
            yield from range(0)

        collections = map(
            is_coll,
            (
                tuple(),
                list(),
                dict(),
                range(0),
                yield_(),
                yield_from(),
            ),
        )
        assert is_coll(collections)
        assert all(collections)

    def test_false(self):
        assert not is_coll("valiant")


@mark.escapeQuotes
class TestQuotes:
    def test_single(
        self,
    ):
        assert escapeSingleQuotes("'valiant'") == "\\'valiant\\'"

    def test_double(self):
        assert escapeDoubleQuotes('"valiant"') == '\\"valiant\\"'

    def test_both(self):
        assert (
            escapeQuotes(f""""valiant" | 'valiant'""")
            == f"\\\"valiant\\\" | \\'valiant\\'"
        )

    def test_join(self):
        assert (
            escapeQuotesJoinMapString('"valiant"', "|", "'valiant'")
            == f"\\\"valiant\\\" | \\'valiant\\'"
        )


@mark.normalizeMultiline
def test_normalizeMultiline(resources):
    assert (
        normalizeMultiline(
            f"""
        Below is the "resources" directory:

        {resources}

    """
        )
        == f'Below is the "resources" directory: {resources}'
    )


@mark.environment
def test_environment():
    _environ = environ.copy()
    with environment(A="a"):
        assert environ["A"] == "a"
    assert environ == _environ


@mark.update
@mark.order(1)
class TestUpdate:
    def test_int(self):
        assert update(dict(a=0, b=2), dict(a=1, c=3)) == dict(a=1, b=2, c=3)

    @parametrized.zip
    def test_string(
        self,
        delimiter=("|", None),
        output=(dict(a="z|a", b="b", c="c"), dict(a="a", b="b", c="c")),
    ):
        assert (
            update(dict(a="z", b="b"), dict(a="a", c="c"), delimiter=delimiter)
            == output
        )

    @parametrized
    def test_coll_append(self, func=(set, list)):
        b = toColl(2, func)
        c = toColl(3, func)
        assert update(
            dict(a=toColl(0, func), b=b),
            dict(a=toColl(1, func), c=c),
        ) == dict(a=toColl((0, 1), func), b=b, c=c)

    @parametrized.zip
    def test_tuple(
        self,
        output=(
            dict(a=(1,), b=(2,), c=(3,)),
            dict(a=(0, 1), b=(2,), c=(3,)),
        ),
        eq=("__eq__", "__ne__"),
    ):
        assert getattr(
            updateWithStrings(dict(a=(0,), b=(2,)), dict(a=(1,), c=(3,))), eq
        )(output)

    @parametrized.zip
    def test_with_strings(
        self,
        output=(
            dict(a="z\na", b="b", c="c"),
            dict(a="a", b="b", c="c"),
        ),
        eq=("__eq__", "__ne__"),
    ):
        assert getattr(updateWithStrings(dict(a="z", b="b"), dict(a="a", c="c")), eq)(
            output
        )
