import json
import os
import sys

from addict import Dict
from collections import namedtuple
from contextlib import contextmanager
from functools import partial
from importlib.machinery import SourceFileLoader, SOURCE_SUFFIXES
from importlib.resources import files
from importlib.util import spec_from_file_location, module_from_spec
from inspect import getfullargspec
from itertools import chain
from more_itertools import collapse
from os import environ, geteuid
from os.path import exists
from pathlib import Path
from rich.console import Console
from rich.padding import Padding
from rich.pretty import pprint, pretty_repr
from rich.text import Text
from shutil import which
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import Iterable

from .path import SuperPath
from .sh import *


def any_in(iterable, *args, not_in=False):
    if not args:
        raise TypeError("any_in() takes at least two argument (1 given)")
    if not_in:
        # Return True if any of the items in args are missing
        return any(arg not in iterable for arg in args)
    else:
        return any(arg in iterable for arg in args)


def all_in(iterable, *args, not_in=False):
    if not args:
        raise TypeError("all_in() takes at least two argument (1 given)")
    if not_in:
        # Return True if all of the items in args are missing
        return all(arg not in iterable for arg in args)
    else:
        return all(arg in iterable for arg in args)


def dirs(obj):
    dct = Dict()
    for attr in dir(obj):
        try:
            dct[attr] = getattr(obj, attr)
        except:
            pass
    return dct


def is_coll(coll):
    if isinstance(coll, (str, bytes, bytearray)):
        return False
    else:
        try:
            iter(coll)
        except TypeError:
            return isinstance(coll, Iterable)
        else:
            return True


def cmapper(func):
    def wrapper(ctx, param, value):
        return map(func, value)

    return wrapper


def ccaller(func):
    def wrapper(ctx, param, value):
        return func(value)

    return wrapper


def parse_tree(tree):
    pass


log_time = True
log_path = True
log_style_mimic = "bold bright_green"
log_style = "not dim " + log_style_mimic


def log_time_format(_):
    text = Text("[" + _.strftime("%H:%M:%S") + "]")
    text.stylize(log_style)
    return text


console = Console(
    log_path=log_path,
    log_time=log_time,
    log_time_format=log_time_format,
    file=sys.stderr,
)
style = "bold #fe1aa4"
log_indent_length = 11
log_indent = " " * log_indent_length


def specialLogIndent(message: str):
    suffix = ": "
    return (
        f"[{style}]"
        + (" " * (log_indent_length - len(message) - len(suffix)))
        + message.upper()
        + suffix
    )


def printPadded(obj):
    console.print(
        Padding(obj, (0, (2 * log_indent_length) if log_time else log_indent_length))
    )


def log(*args, verbose=0):
    if verbose:
        console.log(
            log_indent
            + " ".join(
                str(arg)
                if isinstance(arg, (str, bytes, bytearray))
                else pretty_repr(arg)
                for arg in args
            ),
            style=style,
        )


def notify(*args, verbose=0):
    if verbose:
        console.print()
        console.log(specialLogIndent("note") + " ".join(map(str, args)), style=style)
        console.print()


def warn(*args):
    console.print()
    console.log(
        specialLogIndent("warning") + " ".join(map(str, args)), style="bold yellow"
    )
    console.print()


def cprint(*args):
    console.print()
    console.log(" ".join(map(str, args)), style=style)
    console.print()


chrooted = environ.get("NIX_ENFORCE_PURITY", 0)


# Adapted From:
# Answer: https://stackoverflow.com/a/51575963
# User: https://stackoverflow.com/users/3147711/alex-walczak
@contextmanager
def source_suffixes(*args):
    try:
        SOURCE_SUFFIXES.extend(args)
        yield
    finally:
        del SOURCE_SUFFIXES[-len(args) :]


# Adapted From:
# Answer: https://stackoverflow.com/a/19011259/10827766
# User: https://stackoverflow.com/users/2225682/falsetru
# And: https://www.geeksforgeeks.org/how-to-import-a-python-module-given-the-full-path/#:~:text=Inside%20explicit%20method-,Using%20importlib%20Package,-The%20importlib%20package
def module_installed(path, *args):
    path = SuperPath(path, strict=True)
    name = path.stem
    with TemporaryDirectory() as tmpDirectory:
        tmpDirectory = Path(tmpDirectory)
        tmpFile = tmpDirectory / f"{name}.py"
        path.copy(tmpFile)
        with source_suffixes(*args):
            if spec := spec_from_file_location(name, str(tmpFile)):
                loader = spec.loader
                module = module_from_spec(spec)
            else:
                loader = SourceFileLoader(name, str(tmpFile))
                module = ModuleType(loader.name)
            loader.exec_module(module)
            return module


def conf_to_dict(config):
    conf = Dict()
    for line in config.split("\n"):
        if line:
            split = line.split("=", 1)
            conf[split[0].strip().replace("-", "_")] = split[1].strip()
    return conf


def dict_to_conf(**kwargs):
    return "\n".join(f'{k.replace("_", "-")} = {v}' for k, v in kwargs.items())


def format_conf(conf):
    formatted = ""
    for option in conf.split("\n"):
        if option:
            split = option.split("=", 1)
            formatted += f"{split[0].strip()} = {split[1].strip()}\n"
    return formatted.strip()


# Adapted From:
# Answer: https://stackoverflow.com/a/58941536/10827766
# User: https://stackoverflow.com/users/674039/wim
resources = SuperPath(files("valiant.resources"))
default_config_text = (resources / "nix.conf").read_text()
default_config_dict = conf_to_dict(default_config_text)
updated_config_text = default_config_text
updated_config_dict = Dict(default_config_dict)


def configure(_replace=False, _file=None, _config="", **kwargs):
    global environ
    if isinstance(_file, (str, bytes, bytearray, Path)):
        file = SuperPath(_file).read_text()
    elif _file:
        file = _file.read()
    else:
        file = ""
    if any((_file, _config, kwargs)) and environ.get("NIX_CONFIG", ""):
        if _replace:
            config = "\n".join(
                (format_conf(_config), format_conf(file), dict_to_conf(**kwargs))
            )
        else:
            initial_dict = conf_to_dict(environ["NIX_CONFIG"])
            if _config:
                initial_dict.update(conf_to_dict(_config))
            if _file:
                initial_dict.update(conf_to_dict(file))
            initial_dict.update(kwargs)
            config = dict_to_conf(**initial_dict)
    else:
        config = default_config_text
    environ["NIX_CONFIG"] = config.strip()


@contextmanager
def configuring(**kwargs):
    global environ
    _config = environ.get("NIX_CONFIG", "")
    try:
        configure(**kwargs)
        yield
    finally:
        environ["NIX_CONFIG"] = _config


configure()
resourceLib = "lib=" + str(resources / "lib" / "lib")
if "NIX_PATH" in environ:
    environ["NIX_PATH"] += ":" + resourceLib
else:
    environ["NIX_PATH"] = resourceLib
purity = environ.get("NIX_ENFORCE_PURITY", 0)
building = any(
    environ.get(var, "/tmp") == "/build" for var in ("TMP", "TMPDIR", "TEMP", "TEMPDIR")
)


Output = namedtuple("Output", "stdout stderr returncode")
euid = geteuid()
prompt = "$" if euid else "#"


def escapeSingleQuotes(string):
    return string.replace("'", "\\'")


def escapeDoubleQuotes(string):
    return string.replace('"', '\\"')


def escapeQuotes(string, quotes=0):
    string = str(string)
    if quotes == 1:
        return escapeSingleQuotes(string)
    elif quotes == 2:
        return escapeDoubleQuotes(string)
    else:
        return escapeSingleQuotes(escapeDoubleQuotes(string))


def escapeQuotesJoinMapString(*args):
    return escapeQuotes(" ".join(map(str, args)))


def toColl(item, func):
    if isinstance(item, func):
        return item
    else:
        if issubclass(func, dict):
            try:
                return func(item)
            except TypeError:
                return func({item: None})
        else:
            try:
                return func(item)
            except TypeError:
                return func((item,))


def toTuple(item):
    return toColl(item, tuple)


Defaults = namedtuple("Defaults", "defaults kwargs")


# Adapted from:
# Answer: https://stackoverflow.com/a/218709/10827766
# User Brian: https://stackoverflow.com/users/9493/brian
def getFuncDefaults(func, **kwargs):
    spec = getfullargspec(func)
    args = spec.args
    defaults = spec.defaults or tuple()
    lenDefaults = len(defaults)
    newDefaults = dict()
    for i, d in enumerate(defaults):
        k = args[-lenDefaults:][i]
        newDefaults[k] = kwargs.pop(k, d)
    return Defaults(
        Dict(
            newDefaults
            | {k: kwargs.pop(k, v) for k, v in (spec.kwonlydefaults or dict()).items()}
        ),
        Dict(kwargs),
    )


nixery = ("nix", "nix-shell", "nix-env", "nix-store")
shNixery = ("nix", "nixEval", "nixEvalPure", "nixShell", "nixShellPure")
shBaseOptions = Dict(
    nix_=dict(
        _long_sep=None,
        _err=sys.stderr,
        _truncate_exc=False,
    )
)
shBaseKwargs = Dict(
    nix_=dict(show_trace=True),
    nix=dict(L=True),
    nixEvalPure=dict(raw=True),
)
shBaseKwargs.nixEval = shBaseKwargs.nixEvalPure | dict(impure=True)
shBaseKwargs.nixShellPure = shBaseKwargs.nixShell | dict(pure=True)
shOptions = Dict({prog: shBaseOptions.nix_ | shBaseOptions[prog] for prog in shNixery})
shKwargs = Dict({prog: shBaseKwargs.nix_ | shBaseKwargs[prog] for prog in shNixery})


def chooseShKwargs(prog, sh=SH):
    return shKwargs[prog] if sh == SH else shBaseKwargs[prog]


def chooseShOptions(prog, sh=SH):
    return shOptions[prog] if sh == SH else shBaseOptions[prog]


def chooseShKwargsOpts(prog, sh=SH):
    return chooseShKwargs(prog, sh=sh) | chooseShOptions(prog, sh=sh)


def normalizeMultiline(string):
    split = string.strip().split("\n")
    return " ".join(filter(None, collapse(line.split(" ") for line in split)))


local = SuperPath("~/.local/valiant")
localPath = Path.cwd() if environ.get("NIX_ENFORCE_PURITY", 0) else (local / "PATH")
localPath.mkdir(exist_ok=True, parents=True)
for binary in (
    # "emacs",
    # "nix-shell",
    # "org-tangle",
    # "org-export",
):
    localBin = localPath / binary
    binary = SuperPath(which(binary), strict=True)
    if not localBin.is_symlink():
        localBin.symlink_to(binary)


@contextmanager
def environment(**kwargs):
    global environ
    _environ = environ.copy()
    try:
        environ.update({k: str(v) for k, v in kwargs.items()})
        yield
    finally:
        environ.update(_environ)
        for key in kwargs:
            if key not in _environ:
                del environ[key]


def filterPathList(path):
    split = path.split("\n")
    return filter(exists, collapse(item.split(":") for item in split))


def filterPath(path):
    return ":".join(filterPathList(path))


def format_pkg_string(*pkgs, with_pkgs=tuple(), pkg_string=""):
    return (
        pkg_string
        + " "
        + (
            ("(with " + "; with ".join(with_pkgs) + "; [ " + " ".join(pkgs) + " ])")
            if with_pkgs
            else " ".join(pkgs)
        )
    )


def update(a, b, delimiter=None):
    c = Dict(a)
    for k, v in b.items():
        if k not in a:
            c[k] = v
        elif isinstance(v, dict):
            c[k] = update(c[k], v, delimiter=delimiter)
        elif isinstance(v, list):
            c[k] += v
        elif isinstance(v, set):
            c[k] |= v
        elif (delimiter is not None) and isinstance(v, (str, bytes, bytearray)):
            c[k] += delimiter + v
        else:
            c[k] = v
    return c


def updateWithStrings(a, b):
    return update(a, b, delimiter="\n")


def setOpts(opts, directory, directory_defaults):
    for op in ("tangle", "test", "export", "update"):
        opts[op].enable = opts[op].enable if isinstance(opts[op].enable, bool) else True
    opts.super.test = opts.super.test if isinstance(opts.super.test, bool) else True
    if opts.dirs:
        if is_coll(opts.dirs):
            dirs = opts.dirs
        else:
            dirs = (opts.dirs,)
    else:
        dirs = directory_defaults
    opts.dirs = [SuperPath(directory, d, strict=True) for d in dirs]
    return opts


def getFlake(
    remove=tuple(),
    directory=Path.cwd(),
    ignore_error=False,
    sh=SH,
):
    remove = (
        f'"{r}"'
        for r in chain(
            remove,
            (
                "app",
                "apps",
                "channels",
                "defaultApp",
                "defaultdevShell",
                "defaultDevShell",
                "defaultPackage",
                "defaultTemplate",
                "devShell",
                "devShells",
                "legacyPackages",
                "lib",
                "package",
                "packages",
                "pkgs",
                "superpkgs",
                "template",
                "templates",
            ),
        )
    )
    if (directory / "flake.nix").exists():
        getflake = sh.nix.eval.bake(
            expr=normalizeMultiline(
                f"""

                    with builtins;
                    with ((builtins.getFlake or import) "{resources / "lib"}").lib;
                    let
                        flake = (builtins.getFlake or import) "{directory}";
                        removeNonJSON' = obj:
                            if ((isFunction obj) || (isDerivation obj)) then
                                null
                            else if (isAttrs obj) then
                                (mapAttrs (n: removeNonJSON') obj)
                            else if (isList obj) then
                                (map removeNonJSON' obj)
                            else
                                obj;
                        removeNonJSON = obj:
                            removeNonJSON' (removeAttrs obj (flatten [
                                {" ".join(remove)}
                                systems.doubles.all
                                "outPath"
                            ]));
                        in toJSON (removeNonJSON flake.outputs)

                """
            ),
            **chooseShKwargsOpts("nixEval", sh),
        )
        if ignore_error or chrooted:
            try:
                return Dict(json.loads(getflake()))
            except Exception:
                return Dict()
        else:
            return Dict(json.loads(getflake()))
    else:
        return Dict()


def collectDirs(
    directories,
    all_formats=False,
    dependencies=tuple(),
    first_call=True,
    formats=tuple(),
    sh=SH,
    remove=tuple(),
    skip_dependencies=False,
    optsParser=None,
    log=None,
):
    paths = dict()
    gf = partial(
        getFlake,
        sh=sh,
        ignore_error=True,
        remove=remove,
    )

    def inner(d):
        return setOpts(
            optsParser(
                all_formats=all_formats,
                directory=d,
                format=formats,
                remove=remove,
            )
            if optsParser
            else Dict(),
            d,
            [],
        )

    values = directories.values()
    for directory, flake, opts in zip(
        map(SuperPath, directories.keys()),
        (v if v is None else v["flake"] for v in values),
        (v if v is None else v["opts"] for v in values),
    ):
        if directory.exists():
            flakeOpts = Dict(
                flake=flake or gf(directory=directory),
                opts=opts or inner(directory),
            )
            if skip_dependencies:
                paths[directory] = flakeOpts
            else:
                try:
                    same_dir = (
                        SuperPath(
                            sh.git.bake(C=directory)(
                                "rev-parse",
                                show_toplevel=True,
                            )
                        )
                        == directory
                    )
                except SH.ErrorReturnCode:
                    same_dir = False

                if flakeOpts.opts:
                    odirs = dict()
                    for d in flakeOpts.opts.dirs:
                        dd = SuperPath(directory, d)
                        if dd not in chain(
                            paths.keys(),
                            directories.keys(),
                        ):
                            odirs[dd] = dict(flake=gf(directory=dd), opts=inner(dd))

                    # IMPORTANT: This bit will add the current directory at the end,
                    #            if it is a dependency listed in the `dirs' option.
                    try:
                        del odirs[directory]
                        add_dir = True
                    except KeyError:
                        add_dir = same_dir and (not first_call)

                    paths.update(
                        collectDirs(
                            odirs,
                            all_formats=all_formats,
                            dependencies=dependencies,
                            first_call=False,
                            formats=formats,
                            sh=sh,
                            remove=remove,
                            skip_dependencies=skip_dependencies,
                            optsParser=optsParser,
                            log=log,
                        )
                    )
                    if add_dir:
                        paths[directory] = flakeOpts

                elif same_dir or first_call:
                    paths[directory] = flakeOpts

                if (
                    flakeOpts.flake.valiant
                    or flakeOpts.opts.valiant
                    or any(
                        (directory / file).exists()
                        for file in (
                            "flake.org",
                            "nix.org",
                            ".valiant",
                        )
                    )
                ):
                    paths[directory] = flakeOpts

                if dependencies:
                    filtered_paths = collapse(
                        chain((path,), path.parents)
                        for path in paths.keys()
                        if any(path.match(glob) for glob in dependencies)
                    )
                    paths = {k: v for k, v in paths.items() if k in filtered_paths}

                if log:
                    for path in paths:
                        log(f"Collected {path}...")
    return paths


def write_random(file):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.touch()
    file.write_bytes(os.urandom(1024))


@contextmanager
def filetree():
    with TemporaryDirectory() as tmpdir:
        tmpdir = SuperPath(tmpdir)
        for path in (
            ("a", "b", "c", "d"),
            ("e", "f"),
            ("g", "h", "i"),
            ("g", "h", "j"),
            ("k", "l", "m"),
            ("k", "l", "n"),
            ("k", "l", "o", "p"),
            ("k", "l", "o", "q"),
            "r",
            "s",
            ("t", "u"),
            ("t", "v"),
        ):
            write_random(tmpdir.join(path))
        yield tmpdir
