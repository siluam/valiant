import filecmp
import platform
import shutil
import xxhash

from functools import partial
from more_itertools import collapse
from os import chdir, sep
from os.path import expandvars
from pathlib import Path
from typing import Self


class BasePath(type(Path())):
    def __new__(cls, *args, **kwargs):
        new_args = []
        for arg in map(str, args):
            split = arg.split(sep)
            if split[0].endswith("file:"):
                if split1 := split[1:]:
                    new_args.append(sep.join(split1))
            else:
                new_args.append(arg)
        return super().__new__(cls, *new_args, **kwargs)

    def _from_args(self, *args) -> Self:
        return self._from_parts(collapse(args))

    # Adapted From: https://hg.python.org/cpython/file/151cab576cab/Lib/pathlib.py#l1389
    def expandvars(self) -> Self:
        return self._from_parts(map(expandvars, self._parts))

    def expandboth(self) -> Self:
        return self.expandvars().expanduser()

    def append_suffix(self, *args) -> Self:
        parts = self._parts
        return self._from_args(parts[:-1], parts[-1] + "".join(args))

    def replace_parts(self, old, new) -> Self:
        return self._from_parts(new if part == old else part for part in self._parts)

    # Replace parts partially as well
    def replace_iparts(self, old, new):
        return self._from_parts(part.replace(old, new) for part in self._parts)

    def copytree(self, other, **kwargs):
        dirs_exist_ok = kwargs.pop("dirs_exist_ok", True)
        return shutil.copytree(self, other, dirs_exist_ok=dirs_exist_ok, **kwargs)

    def __getattr__(self, attr):
        if hasattr(shutil, attr):
            return partial(getattr(shutil, attr), self)
        raise AttributeError

    def is_empty(self):
        return self.stat().st_size == 0

    def cmp(self, other, **kwargs):
        if self.is_dir():
            return self.dircmp(other, **kwargs)
        return filecmp.cmp(self, other, **kwargs)

    def deepcmp(self, other, **kwargs):
        kwargs.pop("shallow", None)
        if self.is_dir():
            return self.deepdircmp(other, **kwargs)
        return self.cmp(other, shallow=False, **kwargs)

    @staticmethod
    def _hashcmp(self, other):
        with self.open("rb") as a:
            with open(other, "rb") as b:
                xx = getattr(xxhash, "xxh" + platform.architecture()[0][:2])
                return xx(a.read()).hexdigest() == xx(b.read()).hexdigest()

    def hashcmp(self, other):
        if self.is_dir():
            return self.hashdircmp(other)
        return self._hashcmp(self, other)

    def no_dir(self, item):
        item = self.__class__(item)
        iparts = item._parts
        parts = self._parts
        lparts = len(parts)
        if len(iparts) <= lparts:
            return item
        if iparts[:lparts] == parts:
            return self._from_parts(iparts[lparts:])
        return item

    def items_no_dir(self, items):
        return map(self.no_dir, items)

    def iter_no_dir(self):
        return self.items_no_dir(self.iterdir())

    def glob_no_dir(self, *args):
        return self.items_no_dir(self.glob(*args))

    def rglob_no_dir(self, *args):
        return self.items_no_dir(self.rglob(*args))

    def dircmp(self, other, **kwargs):
        hashes = []
        for item in self.rglob_no_dir("*"):
            a = self / item
            b = self.__class__(other, item)
            if a.is_file() and b.is_file():
                hashes.append(filecmp.cmp(a, b))
            elif a.is_dir() and b.is_dir():
                hashes.append(a.dircmp(b))
            else:
                hashes.append(False)
        return all(hashes)

    def deepdircmp(self, other, **kwargs):
        kwargs.pop("shallow", None)
        return self.dircmp(other, shallow=False, **kwargs)

    def hashdircmp(self, other):
        hashes = []
        for item in self.rglob_no_dir("*"):
            a = self / item
            b = self.__class__(other, item)
            if a.is_file() and b.is_file():
                cmp = self._hashcmp(a, b)
                print("File:", a, b, item, cmp)
                hashes.append(cmp)
            elif a.is_dir() and b.is_dir():
                cmp = a.hashdircmp(b)
                print("Dir:", a, b, item, cmp)
                hashes.append(cmp)
            else:
                print(
                    "Neither:",
                    a,
                    a.is_file(),
                    a.is_dir(),
                    a.exists(),
                    b,
                    b.is_file(),
                    b.is_dir(),
                    b.exists(),
                    item,
                )
                hashes.append(False)
        return all(hashes)

    def join(self, *args):
        return self._from_args(self._parts, args)

    def _print_in(self):
        ...

    def _print_out(self):
        ...

    def __enter__(self):
        self.owd = self.cwd()
        self._print_in()
        chdir(self)
        return self

    def __exit__(self, type, value, tb):
        self._print_out()
        chdir(self.owd)


# Adapted From:
# Answer 1: https://stackoverflow.com/a/34116756/10827766
# User 1: https://stackoverflow.com/users/241039/oleh-prypin
# Answer 2: https://stackoverflow.com/a/53231179/10827766
# User 2: https://stackoverflow.com/users/10630265/a-marchand
# Answer 3: https://stackoverflow.com/a/51699972/10827766
# User 3: https://stackoverflow.com/users/6146442/anton-abrosimov
class SuperPath(BasePath):
    def __new__(cls, *args, strict=False, **kwargs):
        if args:
            if args[0]:
                return (
                    super()
                    .__new__(cls, *args, **kwargs)
                    .expanduser()
                    .resolve(strict=strict)
                )
            else:
                return args[0]
        else:
            return super().__new__(cls).cwd()

    def __init__(self, *args, **kwargs):
        super().__init__()

    @classmethod
    def _process(cls, arg):
        return expandvars(str(arg))

    @classmethod
    def _process_args(cls, args):
        return [cls._process(arg) for arg in args]

    # Adapted From: https://hg.python.org/cpython/file/151cab576cab/Lib/pathlib.py#l51
    def parse_parts(self, parts):
        return super().parse_parts(self._process_args(parts))

    # Adapted From: https://hg.python.org/cpython/file/151cab576cab/Lib/pathlib.py#l616
    @classmethod
    def _parse_args(cls, args):
        return super()._parse_args(cls._process_args(args))
