import orjson as json
import _jsonnet
import dhall
import rapidjson as hujson
import pickle
import xmltodict
import yaml
import tomllib

from addict import Dict
from inspect import ismethod
from pathlib import Path
from tempfile import TemporaryDirectory

from .miscellaneous import (
    getFlake,
    is_coll,
    module_installed,
    chooseShKwargsOpts,
    normalizeMultiline,
    resources,
    update,
)
from .path import SuperPath
from .sh import SH


class Opts:
    __slots__ = (
        "_name",
        "_sh",
        "starlark",
        "bzl",
        "py",
        "vflake",
        "ncl",
    )

    def __init__(
        self,
        name,
        sh=SH,
    ):
        self._name = name
        self._sh = sh
        self.starlark = self.bazel
        self.bzl = self.bazel
        self.py = self.python
        self.vflake = self.flake
        self.ncl = self.nickel

    @property
    def _methods(self):
        return [
            m
            for m in dir(self)
            if m not in self.__slots__
            and not m.startswith("_")
            and ismethod(getattr(self, m))
        ]

    @property
    def _all_methods(self):
        return [
            m for m in dir(self) if not m.startswith("_") and ismethod(getattr(self, m))
        ]

    def pickle(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.pickle"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            with file.open("rb") as handle:
                return pickle.load(handle)
        else:
            return dict()

    def nix(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.nix"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            return json.loads(
                self._sh.nix.eval(
                    expr=normalizeMultiline(
                        f"""

                            with builtins; let
                                convert = v: if (isAttrs v) then (mapAttrs (n: convert) v)
                                        else if (isList v) then (map convert v)
                                        else if (isPath v) then (toString v)
                                        else v;
                            in toJSON (convert (import {file}))

                        """
                    ),
                    **chooseShKwargsOpts("nixEval", self._sh),
                )
            )
        else:
            return dict()

    # NOTE: Be careful when using raw paths with flakes;
    #       since they're sandboxed, they use the nix store as their root directory,
    #       not the current directory. They also can't access parent directories,
    #       as those can't be added to git repos.
    def flake(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name[0]}flake.nix"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            with TemporaryDirectory() as tmpDirectory:
                tmpDirectory = Path(tmpDirectory)
                file.copy(tmpDirectory / "flake.nix")
                (resources / "default.nix").copy(tmpDirectory / "default.nix")
                return getFlake(directory=tmpDirectory, remove=remove, sh=self._sh)
        else:
            return dict()

    def nickel(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.ncl"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            # Adapted From:
            # Answer: https://unix.stackexchange.com/a/700680/270053
            # User: https://unix.stackexchange.com/users/72364/timofey-drozhzhin
            return tomllib.loads(self._sh.nickel.export(format="toml", file=file))

        else:
            return dict()

    def json(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.json"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            return json.loads(file.read_text())
        else:
            return dict()

    def hujson(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.hujson"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            with file.open("rb") as f:
                return hujson.load(
                    f,
                    # Adapted From:
                    # Answer: https://stackoverflow.com/a/67079131/10827766
                    # User: https://stackoverflow.com/users/404906/user404906
                    parse_mode=hujson.PM_COMMENTS | hujson.PM_TRAILING_COMMAS,
                )
        else:
            return dict()

    def toml(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.toml"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            with file.open("rb") as f:
                return tomllib.load(f)
        else:
            return dict()

    def xml(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.xml"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):

            def inner(value):
                if isinstance(value, dict):
                    return {k: inner(v) for k, v in value.items()}
                elif is_coll(value):
                    return [inner(item) for item in value]
                elif isinstance(value, (str, bytes, bytearray)):
                    match value.lower():
                        case "true":
                            return True
                        case "false":
                            return False
                return value

            return inner(xmltodict.parse(file.read_text())["root"])
        else:
            return dict()

    def jsonnet(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.jsonnet"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            return json.loads(
                _jsonnet.evaluate_snippet("valiant", file.read_text(), ext_vars=kwargs)
            )
        else:
            return dict()

    def cue(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.cue"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            return json.loads(self._sh.cue.export(file))
        else:
            return dict()

    def dhall(self, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs):
        file = file or directory / f"{self._name}.dhall"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            return dhall.loads(file.read_text())
        else:
            return dict()

    def _module(
        self, ext, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs
    ):
        file = file or directory / f"{self._name}.{ext}"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            module = module_installed(file, ext)
            return {
                attr: getattr(module, attr)
                for attr in dir(module)
                if not attr.startswith("_")
            }
        else:
            return dict()

    def bazel(self, *args, **kwargs):
        return self._module("bzl", *args, **kwargs)

    def python(self, *args, **kwargs):
        return self._module("py", *args, **kwargs)

    def _yaml(
        self, ext, file=None, directory=Path.cwd(), *args, remove=tuple(), **kwargs
    ):
        file = file or directory / f"{self._name}.{ext}"

        # Adapted From:
        # Answer: https://stackoverflow.com/a/55949699/10827766
        # User: https://stackoverflow.com/users/5422525/m-t
        if file.exists() and (file.stat().st_size != 0):
            return yaml.safe_load(file.read_text())
        else:
            return dict()

    def yaml(self, *args, **kwargs):
        return self._yaml("yaml", *args, **kwargs)

    def yml(self, *args, **kwargs):
        return self._yaml("yml", *args, **kwargs)

    def __call__(
        self,
        file=None,
        directory=Path.cwd(),
        format=None,
        all_formats=False,
        *args,
        remove=tuple(),
        **kwargs,
    ):
        directory = SuperPath(directory, strict=True)
        file = SuperPath(file, strict=True)
        if file:
            return Dict(
                getattr(self, file.suffix[1:])(
                    file, directory, *args, remove=remove, **kwargs
                )
            )
        elif format and isinstance(format, (str, bytes, bytearray)):
            return Dict(
                getattr(self, format)(file, directory, *args, remove=remove, **kwargs)
            )
        else:
            if directory:
                optsDict = dict()
                if format and is_coll(format):
                    for f in format:
                        optsDict = update(
                            optsDict,
                            getattr(self, f)(
                                directory=directory, *args, remove=remove, **kwargs
                            ),
                        )
                    else:
                        return Dict(optsDict)
                else:
                    if all_formats:
                        for format in self._methods:
                            optsDict = update(
                                optsDict,
                                getattr(self, format)(
                                    directory=directory, *args, remove=remove, **kwargs
                                ),
                            )
                        else:
                            return Dict(optsDict)
                    else:
                        for format in self._methods:
                            opts = getattr(self, format)(
                                file=file,
                                directory=directory,
                                *args,
                                remove=remove,
                                **kwargs,
                            )
                            if opts:
                                return Dict(opts)
                        else:
                            return Dict(optsDict)
            else:
                return Dict()
