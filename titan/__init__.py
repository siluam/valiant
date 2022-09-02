#!usr/bin/env python3

import rich.traceback as RichTraceback
RichTraceback.install(show_locals = True)

import click
from addict import Dict
from ast import literal_eval
from collections import namedtuple
from contextlib import contextmanager
from functools import wraps
from io import TextIOWrapper
from pathlib import Path
from rich import print
from rich.console import Console
from subprocess import Popen, PIPE, STDOUT, DEVNULL

output = namedtuple("output", "stdout stderr returncode")

def escapeQuotes(string):
    return str(string).replace('"', '\\"').replace("'", "\\'")

class Gauntlet:
    __slots__ = (
        "dir",
        "sir",
        "verbose",
        "console",
        "status",
        "preFiles",
        "removeTangleBackups",
        "projectName",
        "type",
        "files",
        "updateCommand",
        "inputs",
        "currentSystem",
        "doCheck",
        "testType",
        "doTest",
    )
    def __init__(self, directory, verbose):
        self.dir = directory
        self.sir = str(self.dir)
        self.verbose = verbose

        self.console = Console()
        self.status = self.console.status("[bold orange]Working...")
        self.status.start()

        self.preFiles = " ".join(f"{self.dir}/{file}" for file in ("nix.org", "flake.org", "tests.org", "README.org"))
        self.removeTangleBackups = f"find {self.dir} -name '.\#*.org*' -print | xargs rm &> /dev/null || :"
        self.projectName = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).pname'")
        self.type = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).type'")
        self.files = f"{self.preFiles} {self.dir}/{self.projectName}"
        self.updateCommand = self.fallback(f"nix flake update --show-trace {self.dir}")
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
            if self.verbose:
                self.console.log("Subprocessing Complete!\n")
            if p.returncode and not ignore_stderr:
                raise SystemError("Sorry; something happened! Please check the output of the last command run!")
            if stdout:
                return output(
                    stdout = TextIOWrapper(p.stdout).read().strip() if p.stdout else None,
                    stderr = TextIOWrapper(p.stderr).read().strip() if p.stderr else None,
                    returncode = p.returncode,
                )
        else:
            return command

    def get(self, command, **kwargs):
        return self.run(command, stdout = PIPE, stderr = PIPE, **kwargs)

    def fallbackCommand(self, command, files, get = False):
        self.run(self.removeTangleBackups)
        output = getattr(self, "get" if get else "run")(command)
        if getattr(output, "returncode", 0):
            self.run(f"org-tangle -f {files}", stdout = DEVNULL)
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
        return self.nixShell("cd", self.dir, "&& (", *args[:-1], args[-1] + ")", _type = _type)

    def quickRunInDir(self, pkgs, *args):
        return self.quickRun(pkgs, "cd", self.dir, "&& (", *args[:-1], args[-1] + ")")

    def fallback(self, command, **kwargs):
        return self.fallbackCommand(command, self.files, **kwargs)

    def tangleCommand(self, files):
        self.run(self.removeTangleBackups)
        if getattr(self.run(self.nixShell("org-tangle -f", files, _type = "general")), "returncode", 0):
            return f"org-tangle -f {files}"

    def test(self, *args, _type = None):
        match self.testType:
            case "python": return self.nixShell("pytest", *args, "--suppress-no-test-exit-code", self.dir, _type = _type)
            case _: return None

@click.group()
@click.option("-d", "--directory", default = Path.cwd(), type = Path)
@click.option("-v", "--verbose", is_flag = True)
@click.pass_context
def main(ctx, directory, verbose):
    ctx.ensure_object(dict)
    ctx.obj.cls = Gauntlet(directory = directory, verbose = verbose)

# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786

def gauntletParams(func):
    @click.option("--gauntlet")
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@main.command()
@gauntletParams
@click.pass_context
def add(ctx, gauntlet):
    gauntlet = gauntlet or ctx.obj.cls
    gauntlet.run(f"git -C {gauntlet.dir} add .")

@main.command()
@gauntletParams
@click.pass_context
def commit(ctx, gauntlet):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(add)
    gauntlet.run(f'git -C {gauntlet.dir} commit --allow-empty-message -am ""', ignore_stderr = True)

@main.command()
@gauntletParams
@click.pass_context
def push(ctx, gauntlet):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(commit)
    gauntlet.run(f"git -C {gauntlet.dir} push")

@main.command()
@gauntletParams
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def update(ctx, gauntlet, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(add)
    inputString = ' --update-input '.join(i for i in gauntlet.inputs if not ((i in (
        'nixos-master',
        'nixos-unstable',
    )) or i.endswith('-small')))
    command = f"nix flake lock {gauntlet.dir} --update-input {inputString}"
    if inputs:
        if ("settings" in inputs) and (gauntlet.projectName == "settings"):
            inputs.remove("settings")
        if inputs and (intersection := set(gauntlet.inputs).intersection(inputs)):
            gauntlet.run(gauntlet.fallback(f'nix flake lock {gauntlet.dir} --show-trace --update-input {"--update-input ".join(intersection)}'))
    elif all_inputs:
        gauntlet.run(gauntlet.updateCommand)
    elif gauntlet.projectName == "settings":
        gauntlet.run(command)
    else:
        gauntlet.run(gauntlet.updateCommand)

@main.command()
@gauntletParams
@click.pass_context
def pre_tangle(ctx, gauntlet):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(update, inputs = [ "settings" ])
    gauntlet.run(gauntlet.removeTangleBackups)

@main.command()
@gauntletParams
@click.option("-F", "--local-files", multiple = True, type = Path)
@click.option("-f", "--tangle-files", multiple = True, type = Path)
@click.option("-a", "--all-files", is_flag = True)
@click.pass_context
def tangle(ctx, gauntlet, local_files, tangle_files, all_files):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(pre_tangle)
    local_files = [ (gauntlet.dir / file) for file in local_files ]
    tangle_files = list(tangle_files)
    if all_files:
        gauntlet.run(gauntlet.tangleCommand(" ".join(tangle_files + local_files) + " " + gauntlet.files))
    else:
        gauntlet.run(gauntlet.tangleCommand(" ".join(tangle_files + local_files) or gauntlet.files))
    ctx.invoke(add)

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
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(tangle, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
    ctx.invoke(update, inputs = inputs, all_inputs = all_inputs)

@main.command()
@gauntletParams
@tuParams
@click.option("-d", "--devshell")
@click.pass_context
def develop(ctx, gauntlet, devshell, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    gauntlet.run(f'nix develop --show-trace "{gauntlet.dir}#{devshell or f"makefile-{gauntlet.type}"}"')

@main.command()
@gauntletParams
@tuParams
@click.option("-p", "--pkgs", multiple = True)
@click.option("-P", "--pkg-string")
@click.option("-w", "--with-pkgs", multiple = True)
@click.pass_context
def shell(ctx, gauntlet, pkgs, pkg_string, with_pkgs, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    if pkg_string:
        pass
    elif with_pkgs:
        pkg_string = "(with " + "; with ".join(with_pkgs) + "; [ " + " ".join(pkgs) + " ])"
    else:
        pkg_string = " ".join(pkgs)
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    gauntlet.run(gauntlet.quickShell(pkg_string))

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def repl(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.forward(_tu)
    gauntlet.run(gauntlet.nixShell(gauntlet.type))

@main.command()
@gauntletParams
@tuParams
@click.option("-p", "--pkgs", multiple = True, default = ("default",))
@click.pass_context
def build(ctx, gauntlet, pkgs, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    gauntlet.run(f"""nix build --show-trace "{gauntlet.dir}#{f'" "{gauntlet.dir}#'.join(pkgs)}" """)

@main.command()
@gauntletParams
@tuParams
@click.option("-c", "--command")
@click.pass_context
def cmd(ctx, gauntlet, command, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    gauntlet.run(gauntlet.nixShellInDir(escapeQuotes(command)))

@main.command(name = "run", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.option("-s", "--arg-string")
@click.option("-p", "--pkg", default = "default")
@click.pass_context
def _run(ctx, gauntlet, args, arg_string, pkg, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    gauntlet.run(f"""nix run --show-trace "{gauntlet.dir}#{pkg}" -- {arg_string or " ".join(args)}""")

@main.command(name = "touch-test")
@gauntletParams
@tuParams
@click.argument("test")
@click.pass_context
def touch_test(ctx, gauntlet, test, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    test = escapeQuotes(test)
    gauntlet.run(gauntlet.nixShell("touch", test, "&&", gauntlet.type, test))

@main.command()
@gauntletParams
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.pass_context
def quick(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(tangle, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
    ctx.invoke(push)

@main.command()
@gauntletParams
@tuParams
@click.option("--test/--no-tests", default = True)
@click.pass_context
def super(ctx, gauntlet, test, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(
        _tut if gauntlet.doTest and test else _tu,
        local_files = local_files,
        tangle_files = tangle_files,
        all_files = all_files,
        inputs = inputs,
        all_inputs = all_inputs,
    )
    ctx.invoke(push)

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def poetry2setup(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.forward(_tu)
    gauntlet.run(gauntlet.nixShellInDir(f"poetry2setup > {gauntlet.dir}/setup.py"))

@main.command(name = "touch-tests")
@gauntletParams
@click.pass_context
def touch_tests(ctx, gauntlet):
    gauntlet = gauntlet or ctx.obj.cls
    gauntlet.run(gauntlet.nixShellInDir(f'find {gauntlet.dir}/tests -print | grep -v __pycache__ | xargs touch'), ignore_stderr = True)

@main.command(hidden = True)
@gauntletParams
@tuParams
@click.pass_context
def _tut(ctx, gauntlet, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.forward(_tu)
    ctx.invoke(touch_tests)

@main.command(name = "test")
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.pass_context
def _test(ctx, gauntlet, args, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(_tut, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    gauntlet.run(gauntlet.test(*args))

@main.command(name = "test-native")
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.pass_context
def test_native(ctx, gauntlet, args, local_files, tangle_files, all_files, inputs, all_inputs):
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(
        _test,
        "--tb=native" if gauntlet.testType == "python" else "",
        *args,
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
    gauntlet = gauntlet or ctx.obj.cls
    ctx.invoke(
        _tu,
        local_files = local_files,
        tangle_files = tangle_files,
        all_files = all_files,
        inputs = inputs + [ "titan" "settings" ],
        all_inputs = all_inputs,
    )
    gauntlet.run(f'touch {gauntlet.dir}/.envrc')

@main.command()
@tuParams
@click.argument("dirs", nargs = -1)
@click.option("--test/--no-tests", default = True)
@click.pass_context
def train(ctx, dirs, test, local_files, tangle_files, all_files, inputs, all_inputs):
    for d in dirs:
        ctx.invoke(
            super,
            gauntlet = Gauntlet(directory = d, verbose = ctx.obj.cls.verbose),
            test = test,
            local_files = local_files,
            tangle_files = tangle_files,
            all_files = all_files,
            inputs = inputs,
            all_inputs = all_inputs,
        )

if __name__ == "__main__":
   main(obj=Dict(dict()))
