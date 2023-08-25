import pickle

from pathlib import Path
from pytest import fixture
from string import Template
from valiant import Opts, resources as _resources


# Adapted From:
# Answer: https://stackoverflow.com/a/58941536/10827766
# User: https://stackoverflow.com/users/674039/wim
@fixture
def resources(tmp_path, scope="session"):
    r = tmp_path / "resources"
    r.mkdir()
    _resources.copytree(r, dirs_exist_ok=True)

    # Adapted From: https://www.geeksforgeeks.org/how-to-get-the-permission-mask-of-a-file-in-python/
    mode = tmp_path.stat().st_mode & 0o777

    for item in tmp_path.rglob("*"):
        item.chmod(mode)
    dt = r / "directory_templates"
    pdir = dt / "pickle"
    pdir.mkdir()
    with (pdir / "valiant.pickle").open("wb") as handle:
        pickle.dump(
            dict(dirs=dt / "py", valiant=True),
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    dtv = dt / "valiant.py"
    dtv.write_text(dtv.read_text().replace("...", str(dt)))
    return r


@fixture
def valiance(resources):
    return (v for v in resources.iterdir() if v.stem in ("valiant", "vflake"))


@fixture
def templateDirs(resources):
    dt = resources / "directory_templates"
    templates = [dt / template for template in ("not.valiant",)]
    return sorted(
        directory
        for directory in Path(dt).iterdir()
        if not (
            directory.is_file()
            or directory.name.startswith("_")
            or (directory in templates)
        )
    )


@fixture
def extraneousDirs():
    return dict(nix=3, flake=3, xml=2)


@fixture
def valiantOpts(scope="session"):
    return Opts("valiant")


@fixture
def numberOfDirs(extraneousDirs, valiantOpts):
    return {m: 1 for m in valiantOpts._methods} | extraneousDirs


@fixture
def normalMethods(extraneousDirs, valiantOpts):
    return (m for m in valiantOpts._methods if m not in extraneousDirs.keys())


@fixture
def sumOfDirs(numberOfDirs):
    return sum(numberOfDirs.values())


# Adapted From:
# Answer: https://stackoverflow.com/a/16060908
# User: https://stackoverflow.com/users/1219006/jamylak
@fixture
def templates(resources):
    return {
        t: Template(t.read_text().strip())
        for t in (resources / "directory_templates").iterdir()
        if not t.is_dir()
    }
