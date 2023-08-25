import orjson as json
import pickle
import random
from collections import defaultdict, namedtuple
from os import environ
from pathlib import Path
from pytest import mark, fixture
from rich.pretty import pprint
from string import ascii_lowercase
from tempfile import TemporaryDirectory
from valiant import collectDirs
from functools import partial


@mark.collectDirs
@mark.xdist_group(name="nix")
class TestCollectDirs:
    @fixture
    def collect(self, valiantOpts, scope="class"):
        return partial(collectDirs, optsParser=valiantOpts)

    def test_collect(self):
        pass

    def test_collectAllDirs(self, resources, templateDirs, collect):
        assert (
            sorted(collect({resources / "directory_templates": None}, all_formats=True))
            == templateDirs
        )


# @mark.collectDirs
# @mark.skip
# def test_collectAllDirs(templates, sumOfDirs):
#     Directory = namedtuple("Directory", "dir path")
#     dirs = defaultdict(lambda: Directory(d := TemporaryDirectory(), Path(d.name)))
#     try:
#         ascii_used = []
#         ascii_choices = ascii_lowercase[:sumOfDirs]

#         for path, template in templates.items():
#             c = random.choice(ascii_choices)
#             while c in ascii_used:
#                 c = random.choice(ascii_choices)
#             else:
#                 ascii_used.append(c)
#                 directory = dirs[c].path
#                 (directory / ".valiant").touch()
#                 file = directory / path.name
#                 file.touch()
#                 substitution = dict()
#                 for i in template.get_identifiers():
#                     d = i
#                     while dirs[d].path == directory:
#                         d = random.choice(list(dirs.keys()))
#                     else:
#                         substitution[i] = dirs[d].path
#                 else:
#                     file.write_text(
#                         # Adapted From:
#                         # Answer: https://stackoverflow.com/a/6385940
#                         # User: https://stackoverflow.com/users/129556/thibthib
#                         template.substitute(substitution),
#                         newline="\n",
#                     )

#         with TemporaryDirectory() as root:
#             root = Path(root)
#             with (root / "valiant.pickle").open("wb") as handle:
#                 pickle.dump(
#                     dict(dirs=[str(directory.path) for directory in dirs.values()]),
#                     handle,
#                     protocol=pickle.HIGHEST_PROTOCOL,
#                 )
#             collectedDirs = collectDirs({root: None}, all_formats=True)
#     finally:
#         for directory in dirs.values():
#             directory.dir.cleanup()
