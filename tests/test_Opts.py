from os import environ
from parametrized import parametrized
from pathlib import Path
from pytest import mark, param, fixture
from rich.pretty import pprint
from valiant import Opts, building


@mark.opts
class TestOpts:
    @mark.xml
    def test_xml(self, resources, valiantOpts):
        assert valiantOpts(directory=resources, format="xml") == dict(
            dirs=["./.", "./."]
        )

    @mark.xml
    def test_xml1(self, resources, valiantOpts):
        assert valiantOpts(file=resources / "valiant1.xml") == dict(dirs="./.")

    @mark.xml
    def test_xml2(self, resources, valiantOpts):
        assert valiantOpts(file=resources / "valiant2.xml") == dict(
            dirs="./.",
            valiant=True,
        )

    def test_opts(self, resources, normalMethods, valiantOpts):
        for format in normalMethods:
            assert valiantOpts(directory=resources, format=format) == dict(dirs=["./."])

    @mark.nix
    @mark.xdist_group(name="nix")
    @parametrized
    def test_nix(self, resources, valiantOpts, format=("nix", "flake")):
        dirs = valiantOpts(directory=resources, format=format).dirs
        assert dirs[0] == "./."
        assert "./." not in dirs[1:]

    @mark.nix
    @mark.xdist_group(name="nix")
    @parametrized
    def test_rest_of_nix(
        self,
        resources,
        valiantOpts,
        format=(
            "nix",
            param(
                "flake",
                marks=mark.skipif(
                    building, reason="Fails in a nix chroot because of flake sandbox."
                ),
            ),
        ),
    ):
        dirs = valiantOpts(directory=resources, format=format).dirs
        assert all(path.exists() for path in map(Path, dirs[1:]))

    @mark.skipif(building, reason="Fails in a nix chroot because of flake sandbox.")
    def test_all(self, resources, sumOfDirs, valiantOpts):
        dirs = valiantOpts(directory=resources, all_formats=True).dirs
        assert all((d == "./." or Path(d).exists()) for d in dirs)
        assert len(dirs) == sumOfDirs
