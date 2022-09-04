#!usr/bin/env python3

import rich.traceback as RichTraceback
RichTraceback.install(show_locals = True)

import click
import json
from addict import Dict
from ast import literal_eval
from collections import namedtuple
from contextlib import contextmanager
from functools import wraps
from io import TextIOWrapper
from os import chdir
from pathlib import Path
from rich import print
from rich.console import Console
from subprocess import Popen, PIPE, STDOUT, DEVNULL

output = namedtuple("output", "stdout stderr returncode")

def escapeQuotes(string):
    return str(string).replace('"', '\\"').replace("'", "\\'")

class Gauntlet:
    __slots__ = (
        "color",
        "console",
        "currentSystem",
        "dir",
        "doCheck",
        "doTest",
        "file",
        "files",
        "inputs",
        "opts",
        "preFiles",
        "projectName",
        "sir",
        "status",
        "testType",
        "type",
        "updateCommand",
        "verbose",
    )
    def __init__(self, directory, verbose = False, opts = None, console = None, status = None):
        self.dir = directory
        if Path.cwd() != self.dir:
            chdir(self.dir)

        self.sir = str(self.dir)
        self.verbose = verbose

        self.file = self.dir / "titan.json"
        if self.file.exists():
            with open(self.file) as f:
                self.opts = (opts or {}) | Dict(json.load(f))
        else:
            self.opts = opts or Dict()
        self.opts.test.args = self.opts.test.args or []

        self.console = console
        self.status = status

        self.preFiles = " ".join(f"{self.dir}/{file}" for file in ("nix.org", "flake.org", "tests.org", "README.org"))
        self.projectName = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).pname'")
        self.type = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).type'")
        self.files = f"{self.preFiles} {self.dir}/{self.projectName}"
        self.updateCommand = f"nix flake update --show-trace {self.dir}"
        self.inputs = literal_eval(literal_eval(self.getPreFallback(f"""nix eval --show-trace --impure --expr 'with (import {self.dir}); with (inputs.settings.lib or inputs.nixpkgs.lib); "[ \\"" + (concatStringsSep "\\", \\"" (attrNames inputs)) + "\\" ]"'""").stdout))
        self.currentSystem = self.getPFbWQ("nix eval --show-trace --impure --expr builtins.currentSystem")
        self.doCheck = literal_eval(self.getPreFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).packages.{self.currentSystem}.default.doCheck'").stdout.capitalize())
        self.testType = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).testType'")
        self.doTest = self.doCheck or ((self.type != "general") and (self.testType != "general"))

    @contextmanager
    def pauseStatus(self, pred):
        if pred:
            self.status.stop()
            yield
            self.status.start()
        else:
            yield

    def run(self, command, stdout = None, stderr = STDOUT, ignore_stderr = False):
        if isinstance(command, (str, bytes, bytearray)):
            command = command.strip()
            if self.verbose:
                verboseCommand = "\n".join(("           " + line) if index else line for index, line in enumerate(command.split("\n")))
                self.console.log(f"Subprocessing Command: {verboseCommand}")
            with self.pauseStatus(stdout is None and any(cmd in command for cmd in (
                "org-tangle",
                "nix flake update",
                "nix flake lock",
                "nix build",
                "nix run",
                "nix develop",
                "nix-shell",
                f"git -C {self.dir} commit",
                f"git -C {self.dir} push",
            ))):
                p = Popen(command, shell = True, stdout = stdout, stderr = stderr)
                p.wait()
            if p.returncode and not ignore_stderr:
                raise SystemError(f"Sorry; something happened! Please check the output of the last command run:\n\n{command}\n")
            if self.verbose:
                self.console.log("Subprocessing Complete!\n")
            return output(
                stdout = TextIOWrapper(p.stdout).read().strip() if p.stdout else None,
                stderr = TextIOWrapper(p.stderr).read().strip() if p.stderr else None,
                returncode = p.returncode,
            )
        else:
            return command

    def removeTangleBackups(self):
        self.run(f"find {self.dir} -name '.\#*.org*' -print | xargs rm", stdout = DEVNULL, stderr = DEVNULL, ignore_stderr = True)

    def get(self, command, **kwargs):
        return self.run(command, stdout = PIPE, stderr = PIPE, **kwargs)

    def runGit(self, command, **kwargs):
        return self.run(f"""git -C {self.dir} {command}""", **kwargs)

    def getGit(self, command, **kwargs):
        return self.get(f"""git -C {self.dir} {command}""", **kwargs)

    def fallbackCommand(self, command, files, get = False):
        output = getattr(self, "get" if get else "run")(command, ignore_stderr = True)
        if output.returncode:
            self.removeTangleBackups()
            self.run(f"org-tangle -f {files}", stdout = DEVNULL if get else None)
            return command
        else:
            return output

    def preFallback(self, command, **kwargs):
        return self.fallbackCommand(command, self.preFiles, **kwargs)

    def getPreFallback(self, command, **kwargs):
        return self.get(self.preFallback(command, get = True), **kwargs)

    def getPFbWQ(self, command, **kwargs):
        return self.getPreFallback(command, **kwargs).stdout.strip('"')

    def nixShell(self, *args, _type = None):
        return f"""nix-shell -E '(import {self.dir}).devShells.{self.currentSystem}.makefile-{_type or self.type}' --show-trace --run "{escapeQuotes(' '.join(map(str, args)))}" """

    def quickShell(self, pkgs):
        return f"""nix-shell -E 'with (import {self.dir}).pkgs.{self.currentSystem}; with lib; mkShell {{ buildInputs = flatten [ " + {pkgs} + " ]; }}' --show-trace"""

    def quickRun(self, pkgs, *args):
        return self.quickShell(pkgs) + f""" --run "{escapeQuotes(' '.join(map(str, args)))}" """

    def nixShellInDir(self, *args, _type = None):
        return self.nixShell("cd", self.dir, "&& (", *args[:-1], args[-1], ")", _type = _type)

    def quickRunInDir(self, pkgs, *args):
        return self.quickRun(pkgs, "cd", self.dir, "&& (", *args[:-1], args[-1] + ")")

    def _fallback(self, command, get = False):
        return self.fallbackCommand(command, self.files, get = get)

    def fallback(self, command, get = False, **kwargs):
        return self.run(self._fallback(command, get = get), **kwargs)

    def tangleCommand(self, files):
        self.removeTangleBackups()
        if self.run(self.nixShell("org-tangle -f", files, _type = "general"), ignore_stderr = True).returncode:
            return f"org-tangle -f {files}"

    def test(self, *args, _type = None):
        if self.opts.test.cmd:
            return self.nixShell(self.opts.test.cmd)
        else:
            args = list(args) + self.opts.test.args
            match self.testType:
                case "python": return self.nixShell("pytest", *args, "--suppress-no-test-exit-code", self.dir, _type = _type)
                case _: return None

filename = "titan.json"
optsdirname = Path("~/.config/titan").resolve()
optsfilename = (optsdirname / filename).resolve()
cwd = Path.cwd()

@click.group()
@click.option("-d", "--dirs", default = (cwd,), type = Path, multiple = True)
@click.option("-O", "--opts-file", help = "Path to a global options file.")
@click.option("-o", "--opts-dir", help = f'Path to a directory with a global options file "{filename}".')
@click.option("-v", "--verbose", is_flag = True)
@click.pass_context
def main(ctx, dirs, opts_file, opts_dir, verbose):
    ctx.ensure_object(dict)

    if (opts_file and Path(opts_file).resolve().exists()) or (opts_dir and (opts_file := Path(opts_dir).resolve() / filename).exists()) or (opts_file := optsfilename):
        chdir(opts_file.parent)
        with open(opts_file) as f:
            ctx.obj.opts = Dict(json.load(f))
    else:
        ctx.obj.opts = Dict()

    ctx.obj.console = Console()
    ctx.obj.color = "bold salmon1"
    ctx.obj.status = ctx.obj.console.status(f"[{ctx.obj.color}]Working...", spinner_style = ctx.obj.color)
    ctx.obj.status.start()

    ctx.obj.cls = [ Gauntlet(
        directory = d,
        verbose = verbose,
        console = ctx.obj.console,
        status = ctx.obj.status
    ) for d in [ Path(d).resolve(strict = True) for d in list(dirs) + ctx.obj.opts.dirs ] ]

# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786

def gauntletParams(func):
    @click.option("-g", "--gauntlet")
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@main.command()
@gauntletParams
@click.pass_context
def add(ctx, gauntlet):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        g.runGit(f"add .")

@main.command()
@gauntletParams
@click.pass_context
def commit(ctx, gauntlet):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(add, gauntlet = g)
        g.runGit(f'commit --allow-empty-message -am ""', ignore_stderr = True)

@main.command()
@gauntletParams
@click.pass_context
def push(ctx, gauntlet):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(commit, gauntlet = g)
        if not g.getGit("status").split("\n")[1].startswith("Your branch is up to date"):
            g.runGit(f"push")

@main.command()
@gauntletParams
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def update(ctx, gauntlet, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(add, gauntlet = g)
        inputString = ' --update-input '.join(i for i in g.inputs if not ((i in (
            'nixos-master',
            'nixos-unstable',
        )) or i.endswith('-small')))
        command = f"nix flake lock {g.dir} --update-input {inputString}"
        if inputs:
            if ("settings" in inputs) and (g.projectName == "settings"):
                inputs.remove("settings")
            if inputs and (intersection := set(g.inputs).intersection(inputs)):
                g.fallback(f'nix flake lock {g.dir} --show-trace --update-input {"--update-input ".join(intersection)}')
        elif all_inputs:
            g.fallback(g.updateCommand)
        elif g.projectName == "settings":
            g.fallback(command)
        else:
            g.fallback(g.updateCommand)

@main.command()
@gauntletParams
@click.option("-F", "--local-files", multiple = True, type = Path)
@click.option("-f", "--tangle-files", multiple = True, type = Path)
@click.option("-a", "--all-files", is_flag = True)
@click.pass_context
def tangle(ctx, gauntlet, local_files, tangle_files, all_files):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(update, gauntlet = g, inputs = [ "settings" ])
        local_files = [ (g.dir / file) for file in local_files ]
        tangle_files = list(tangle_files)
        if all_files:
            g.run(g.tangleCommand(" ".join(tangle_files + local_files) + " " + g.files))
        else:
            g.run(g.tangleCommand(" ".join(tangle_files + local_files) or g.files))
        ctx.invoke(add, gauntlet = g)
        checkCommand = f"nix flake check --show-trace {g.dir}"
        if g.run(checkCommand, ignore_stderr = True).returncode:
            ctx.invoke(update, gauntlet = g)
            g.run(checkCommand)

@main.command()
@gauntletParams
@click.option("-F", "--local-files", multiple = True, type = Path)
@click.option("-f", "--tangle-files", multiple = True, type = Path)
@click.option("-a", "--all-files", is_flag = True)
@click.pass_context
def check(ctx, gauntlet, local_files, tangle_files, all_files):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(tangle, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files)

# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786

def tuParams(func):
    @click.option("-F", "--local-files", multiple = True, default = [])
    @click.option("-f", "--tangle-files", multiple = True, default = [])
    @click.option("-A", "--all-files", is_flag = True)
    @click.option("-i", "--inputs", multiple = True, default = [])
    @click.option("-a", "--all-inputs", is_flag = True)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@main.command(hidden = True)
@gauntletParams
@tuParams
@click.pass_context
def _tu(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(tangle, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
        ctx.invoke(update, gauntlet = g, inputs = inputs, all_inputs = all_inputs)

@main.command()
@gauntletParams
@tuParams
@click.option("-d", "--devshell")
@click.pass_context
def develop(ctx, gauntlet, devshell, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(f'nix develop --show-trace "{g.dir}#{devshell or f"makefile-{g.type}"}"')

@main.command()
@gauntletParams
@tuParams
@click.option("-p", "--pkgs", multiple = True)
@click.option("-P", "--pkg-string")
@click.option("-w", "--with-pkgs", multiple = True)
@click.pass_context
def shell(ctx, gauntlet, pkgs, pkg_string, with_pkgs, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        if pkg_string:
            pass
        elif with_pkgs:
            pkg_string = "(with " + "; with ".join(with_pkgs) + "; [ " + " ".join(pkgs) + " ])"
        else:
            pkg_string = " ".join(pkgs)
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.quickShell(pkg_string))

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def repl(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.nixShell(g.type))

@main.command()
@gauntletParams
@tuParams
@click.option("-p", "--pkgs", multiple = True, default = ("default",))
@click.pass_context
def build(ctx, gauntlet, pkgs, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(f"""nix build --show-trace "{g.dir}#{f'" "{g.dir}#'.join(pkgs)}" """)

@main.command()
@gauntletParams
@tuParams
@click.option("-c", "--command")
@click.pass_context
def cmd(ctx, gauntlet, command, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.nixShellInDir(escapeQuotes(command)))

@main.command(name = "run", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.option("-s", "--arg-string")
@click.option("-p", "--pkg", default = "default")
@click.pass_context
def _run(ctx, gauntlet, args, arg_string, pkg, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(f"""nix run --show-trace "{g.dir}#{pkg}" -- {arg_string or " ".join(args)}""")

@main.command(name = "touch-test")
@gauntletParams
@tuParams
@click.argument("test")
@click.pass_context
def touch_test(ctx, gauntlet, test, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        test = escapeQuotes(test)
        g.fallback(g.nixShell("touch", test, "&&".type, test))

@main.command()
@gauntletParams
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-n", "--do-not-push", is_flag = True)
@click.pass_context
def quick(ctx, gauntlet, local_files, tangle_files, all_files, do_not_push):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(tangle, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
        if not do_not_push:
            ctx.invoke(push, gauntlet = g)

@main.command()
@gauntletParams
@tuParams
@click.option("--test/--no-tests", default = True)
@click.option("-n", "--do-not-push", is_flag = True)
@click.pass_context
def super(ctx, gauntlet, test, local_files, tangle_files, all_files, inputs, all_inputs, do_not_push):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(
            _tut if g.doTest and test else _tu,
            gauntlet = g,
            local_files = local_files,
            tangle_files = tangle_files,
            all_files = all_files,
            inputs = inputs,
            all_inputs = all_inputs,
        )
        if not do_not_push:
            ctx.invoke(push, gauntlet = g)

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def poetry2setup(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.nixShellInDir(f"poetry2setup > {g.dir}/setup.py"))

@main.command(name = "touch-tests")
@gauntletParams
@click.pass_context
def touch_tests(ctx, gauntlet):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        g.run(f'find {g.dir}/tests -print | grep -v __pycache__ | xargs touch', stdout = DEVNULL, stderr = DEVNULL, ignore_stderr = True)

@main.command(hidden = True)
@gauntletParams
@tuParams
@click.pass_context
def _tut(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tu, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        ctx.invoke(touch_tests, gauntlet = g)

@main.command(name = "test")
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.pass_context
def _test(ctx, gauntlet, args, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(_tut, gauntlet = g, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.test(*args))

@main.command(name = "test-native")
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.pass_context
def test_native(ctx, gauntlet, args, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(
            _test,
            "--tb=native" if g.testType == "python" else "",
            *args,
            gauntlet = g,
            local_files = local_files,
            tangle_files = tangle_files,
            all_files = all_files,
            inputs = inputs,
            all_inputs = all_inputs,
        )

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def up(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else ctx.obj.cls:
        ctx.invoke(
            _tu,
            gauntlet = g,
            local_files = local_files,
            tangle_files = tangle_files,
            all_files = all_files,
            inputs = inputs + [ "titan" "settings" ],
            all_inputs = all_inputs,
        )
        g.run(f'touch {g.dir}/.envrc')

if __name__ == "__main__":
    obj=Dict(dict())
    try:
        main(obj=obj)
    finally:
        try:
            obj.status.stop()
        except Exception:
            pass