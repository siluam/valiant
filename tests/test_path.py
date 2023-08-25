from parametrized import parametrized
from os.path import expandvars
from pathlib import Path
from pytest import mark, param, fixture
from tempfile import TemporaryDirectory
from uuid import uuid1
from valiant import building, filetree
from valiant.path import BasePath, SuperPath


@mark.path
class TestPath:
    def test_path(self):
        assert SuperPath("valiant") == Path("valiant").resolve()

    def test_expand_HOME(self):
        assert SuperPath("$HOME") != Path("$HOME")

    def test_resolve_expand_HOME(self):
        assert SuperPath("$HOME") != Path("$HOME").resolve()

    def test_expandvars(self):
        assert SuperPath("$HOME") == Path.home()

    @parametrized
    def test_expandhome(
        self,
        home=(
            "~",
            param(
                "~$USER",
                marks=mark.skipif(
                    building,
                    reason="Fails in a nix chroot because user isn't available.",
                ),
            ),
        ),
    ):
        assert SuperPath(home) == Path.home()

    def test_no_path(self):
        assert SuperPath() == Path.cwd()

    @parametrized
    def test_none(self, obj=(None, "", 0)):
        assert SuperPath(obj) is obj

    @mark.xfail(raises=FileNotFoundError)
    def test_strict(self):
        assert SuperPath(uuid1(), strict=True)

    def test_instance(self):
        for path in (SuperPath(), SuperPath() / "valiant"):
            assert isinstance(path, SuperPath)
            assert isinstance(path, BasePath)
            assert isinstance(path, Path)

    def test_variable_expansion(self):
        assert (
            (SuperPath() / "$HOME")
            == SuperPath("$HOME")
            == SuperPath.home()
            == BasePath("$HOME").expandvars()
            == BasePath("$HOME").expandboth()
            == BasePath.home()
            == Path(expandvars("$HOME"))
            == Path.home()
        )

    def test_variable(self):
        assert Path("$HOME") == BasePath("$HOME") != SuperPath("$HOME")

    def test_chdir(self):
        cwd = Path.cwd()
        with SuperPath.home():
            assert Path.cwd() == Path.home()
        assert Path.cwd() == cwd

    def test_append_suffix(self):
        assert SuperPath().append_suffix(".txt") == Path().cwd().with_suffix(".txt")

    def test_append_multiple_suffix(self):
        assert SuperPath().append_suffix(".txt", ".bak") != Path.cwd().with_suffix(
            ".txt"
        ).with_suffix(".bak")

    def test_append_multiple_suffix_value(self):
        assert SuperPath().append_suffix(".txt", ".bak") == Path.cwd().with_suffix(
            ".txt.bak"
        )


@mark.path
class TestShutil(TestPath):
    @fixture
    def ft(self):
        with filetree() as ft:
            yield ft

    @fixture
    def ftmp(self, ft, tmp_path):
        ft.copytree(tmp_path)
        yield ft, tmp_path

    def test_rmtree(self, ft):
        ft.rmtree()
        assert not ft.exists()


@mark.path
@mark.usefixtures("ft", "ftmp")
class TestCompare(TestShutil):
    @fixture
    def r2(self, ft):
        return ft / "e" / "r"

    @fixture
    def r1(self, r2):
        r1 = r2.parent.parent / "r"
        r1.copy(r2)
        return r1

    def test_file_compare(self, r1, r2):
        assert r1.cmp(r2)

    def test_deep_file_compare(self, r1, r2):
        assert r1.deepcmp(r2)

    def test_hash_file_compare(self, r1, r2):
        assert r1.hashcmp(r2)

    def test_dir_compare(self, ftmp):
        assert ftmp[0].cmp(ftmp[1])

    def test_deep_dir_compare(self, ftmp):
        assert ftmp[0].deepcmp(ftmp[1])

    def test_hash_dir_compare(self, ftmp):
        print(sorted(ftmp[0].rglob("*")))
        assert ftmp[0].hashcmp(ftmp[1])
