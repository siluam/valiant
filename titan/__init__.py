#!usr/bin/env python3

import rich.traceback as RichTraceback
RichTraceback.install(show_locals = True)

import click
import json
from addict import Dict
from ast import literal_eval
from collections import namedtuple
from contextlib import contextmanager
from functools import wraps, partial
from os import chdir, geteuid
from pathlib import Path
from queue import Queue, Empty
from rich import print
from rich.console import Console
from subprocess import Popen, PIPE, STDOUT, DEVNULL
from threading import Thread

Output = namedtuple("Output", "stdout stderr returncode")
euid = geteuid()
prompt = "$" if euid else "#"

def escapeQuotes(string):
    return str(string).replace('"', '\\"').replace("'", "\\'")

class Gauntlet:
    __slots__ = (
        "color",
        "console",
        "currentSystem",
        "dir",
        "doCheck",
        "file",
        "tangle_files",
        "export_files",
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
        self.opts.export.ef = self.opts.export.ef or []
        self.opts.super.test = self.opts.super.test if isinstance(self.opts.super.test, bool) else True

        self.console = console
        self.status = status

        self.preFiles = " ".join(f"{self.dir}/{file}" for file in ("nix.org", "flake.org", "tests.org", "README.org", "index.org"))
        self.projectName = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).pname'")
        self.type = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).type'")
        self.tangle_files = f"{self.preFiles} {self.dir}/{self.projectName}"
        self.export_files = [ (self.dir / file).resolve() for file in ("index.org",) ]
        self.updateCommand = f"nix flake update --show-trace {self.dir}"
        self.inputs = literal_eval(literal_eval(self.getPreFallback(f"""nix eval --show-trace --impure --expr 'with (import {self.dir}); with (inputs.settings.lib or inputs.nixpkgs.lib or (import <nixpkgs> {{}}).lib); "[ \\"" + (concatStringsSep "\\", \\"" (attrNames inputs)) + "\\" ]"'""").stdout))
        self.currentSystem = self.getPFbWQ("nix eval --show-trace --impure --expr builtins.currentSystem")
        self.doCheck = literal_eval(self.getPreFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).packages.{self.currentSystem}.default.doCheck or false'").stdout.capitalize())
        self.testType = self.getPFbWQ(f"nix eval --show-trace --impure --expr '(import {self.dir}).testType'")

    def __eq__(self, directory):
        return directory in (self.dir, self.sir)

    @contextmanager
    def pauseStatus(self, pred):
        if pred:
            self.status.stop()
            yield
            self.status.start()
        else:
            yield

    def warn(self, warning):
        self.console.rule("[bold yellow]WARNING", style = "bold yellow")
        self.console.log("           " + warning, style = "bold yellow")
        self.console.rule("[bold yellow]WARNING", style = "bold yellow")
        self.console.log(f"\n")

    def run(self, command, stdout = None, stderr = STDOUT, ignore_stderr = False):
        if isinstance(command, (str, bytes, bytearray)):
            q = Queue()
            stdoutValue = []
            stderrValue = []
            def inner(pStd, vStd):
                if pStd:
                    for line in pStd:
                        line = (line.decode("utf-8") if isinstance(line, (bytes, bytearray)) else line).strip()
                        vStd.append(line)
                        q.put(line)
            command = command.strip()
            if self.verbose:
                verboseCommand = "\n".join(("           " + line) if index else line for index, line in enumerate(command.split("\n")))
                self.console.log(f"           Subprocessing Command: {verboseCommand}")
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
                p = Popen(command, shell = True, stdout = stdout, stderr = stderr, bufsize = 1, universal_newlines = True, close_fds=True)
                o = Thread(target=inner, args=(p.stdout, stdoutValue))
                o.daemon = True
                o.start()
                e = Thread(target=inner, args=(p.stderr, stderrValue))
                e.daemon = True
                e.start()
                p.wait()
            output = Output(
                stdout = "\n".join(stdoutValue) if stdoutValue else None,
                stderr = "\n".join(stderrValue) if stderrValue else None,
                returncode = p.returncode,
            )
            if (p.returncode > 0) and not ignore_stderr:
                raise SystemError(f"Sorry; something happened! Please check the output of the last command run:\n\n{command}\n\n#######\nSTDERR:\n#######\n\n{output.stderr}\n\n###########\nRETURNCODE:\n###########\n\n{output.returncode}")
            if self.verbose:
                message = "           Subprocessing Complete! Value: "
                indentedOutput = "\n".join(((" " * len(message)) + line) if index else line for index, line in enumerate(output.stdout.split("\n"))) if output.stdout else output.stdout
                self.console.log(f"{message}{indentedOutput}\n")
            return output
        else:
            return command

    def runInDir(self, command, **kwargs):
        self.run(f"""cd "{self.dir}" && ({command})""", **kwargs)

    def removeTangleBackups(self):
        self.run(f"find {self.dir} \( -name '*.*~' -o -name '#*.org*' \) -print | xargs rm", stdout = DEVNULL, stderr = DEVNULL, ignore_stderr = True)

    def get(self, command, **kwargs):
        return self.run(command, stdout = PIPE, stderr = PIPE, **kwargs)

    def getInDir(self, command, **kwargs):
        return self.get(f"""cd "{self.dir}" && ({command})""", **kwargs)

    def runGit(self, command, **kwargs):
        return self.run(f"""git -C {self.dir} {command}""", **kwargs)

    def getGit(self, command, **kwargs):
        return self.get(f"""git -C {self.dir} {command}""", **kwargs).stdout.strip('"')

    def fallbackCommand(self, command, files, get = False, **kwargs):
        stdout = DEVNULL if get else None
        if not Path(self.dir / "flake.nix").exists():
            self.run(f"org-tangle -f {files}", stdout = stdout)
        if not Path(self.dir / "flake.lock").exists():
            self.runGit(f"add .", stdout = stdout)
            self.run(f"nix flake update {self.dir}", stdout = stdout)
        output = getattr(self, "get" if get else "run")(command, ignore_stderr = True, **kwargs)
        if output.returncode > 0:
            self.removeTangleBackups()
            self.run(f"org-tangle -f {files}", stdout = stdout)
            return command
        else:
            return output

    def preFallback(self, command, get = False, **kwargs):
        return self.fallbackCommand(command, self.preFiles, get = get, **kwargs)

    def getPreFallback(self, command, **kwargs):
        return self.get(self.preFallback(command, get = True, **kwargs), **kwargs)

    def getPFbWQ(self, command, **kwargs):
        return self.getPreFallback(command, **kwargs).stdout.strip('"')

    def nixShell(self, *args, _type = None):
        return f"""nix-shell -E '(import {self.dir}).devShells.{self.currentSystem}.makefile-{_type or self.type}' --show-trace --run "{escapeQuotes(' '.join(map(str, args)))}" """

    def quickShell(self, pkgs):
        return f"""nix-shell -E 'with (import {self.dir}).pkgs.{self.currentSystem}; with lib; mkShell {{ buildInputs = flatten [ " + {pkgs} + " ]; }}' --show-trace"""

    def quickRun(self, pkgs, *args):
        return self.quickShell(pkgs) + f""" --run "{escapeQuotes(' '.join(map(str, args)))}" """

    def nixShellInDir(self, *args, _type = None):
        return self.nixShell("cd", f'"{self.dir}"', "&& (", *args[:-1], args[-1], ")", _type = _type)

    def quickRunInDir(self, pkgs, *args):
        return self.quickRun(pkgs, "cd", f'"{self.dir}"', "&& (", *args[:-1], args[-1] + ")")

    def _fallback(self, command, get = False, **kwargs):
        return self.fallbackCommand(command, self.tangle_files, get = get, **kwargs)

    def fallback(self, command, get = False, **kwargs):
        return self.run(self._fallback(command, get = get, **kwargs), **kwargs)

    def tangleCommand(self, files):
        self.removeTangleBackups()
        if self.run(self.nixShell("org-tangle -f", files, _type = "general"), ignore_stderr = True).returncode > 0:
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
optsdirname = Path(f"{Path.home()}/.config/titan").resolve()
optsfilename = (optsdirname / filename).resolve()
cwd = Path.cwd()

@click.group()
@click.option("-d", "--dirs", multiple = True)
@click.option("-O", "--opts-file", help = "Path to a global options file.")
@click.option("-o", "--opts-dir", help = f'Path to a directory with a global options file "{filename}".')
@click.option("-v", "--verbose", is_flag = True)
@click.pass_context
def main(ctx, dirs, opts_file, opts_dir, verbose):
    ctx.ensure_object(dict)

    if (opts_file and Path(opts_file).resolve().exists()) or (opts_dir and (opts_file := Path(opts_dir).resolve() / filename).exists()) or (opts_file := optsfilename).exists():
        chdir(opts_file.parent)
        with open(opts_file) as f:
            ctx.obj.opts = Dict(json.load(f))
    else:
        ctx.obj.opts = Dict()

    ctx.obj.opts.dirs = ctx.obj.opts.dirs or [ cwd ]

    ctx.obj.console = Console(log_path = False, log_time = False)
    ctx.obj.color = "bold green"
    ctx.obj.status = ctx.obj.console.status(f"[{ctx.obj.color}]Working...", spinner_style = ctx.obj.color)
    ctx.obj.status.start()

    ctx.obj.paths = [ Path(d).resolve(strict = True) for d in list(dirs) + ctx.obj.opts.dirs ]
    ctx.obj.mkGauntlet = partial(
        Gauntlet,
        verbose = verbose,
        console = ctx.obj.console,
        status = ctx.obj.status
    )

# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786

def gauntletParams(func):
    @click.option("--gauntlet")
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@main.command()
@gauntletParams
@click.argument("fds", nargs = -1, required = False)
@click.pass_context
def add(ctx, fds, gauntlet):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        g.runGit(f"""add {" ".join(fds or (".",))}""")

@main.command()
@gauntletParams
@click.pass_context
@click.option("-f", "--fds", multiple = True)
@click.argument("message", required = False)
def commit(ctx, message, gauntlet, fds):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(add, fds = fds, gauntlet = g)
        g.runGit(f"""commit --allow-empty-message -am "{message or ""}" """, ignore_stderr = True)

@main.command()
@gauntletParams
@click.option("-f", "--fds", multiple = True)
@click.option("-n", "--do-not-push", is_flag = True)
@click.argument("message", required = False)
@click.pass_context
def push(ctx, message, gauntlet, fds, do_not_push):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(commit, message = message, gauntlet = g, fds = fds)

        # Keep the order of the conditional here, as we want this to be in the verbose output if necessary.
        if not (g.getGit("status").split("\n")[1].startswith("Your branch is up to date") or do_not_push):
            g.runGit(f"push")

@main.command()
@gauntletParams
@click.argument("inputs", nargs = -1, required = False)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def update(ctx, gauntlet, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(add, gauntlet = g)
        if inputs and ("settings" in inputs) and (g.projectName == "settings"):
            inputs.remove("settings")
        inputString = ' --update-input '.join(i for i in g.inputs if not ((i in (
            'nixos-master',
            'nixos-unstable',
        )) or i.endswith('-small')))
        command = f"nix flake lock {g.dir} --show-trace --update-input {inputString}"
        if inputs:
            if (intersection := set(g.inputs).intersection(inputs)):
                g.fallback(f'nix flake lock {g.dir} --show-trace --update-input {"--update-input ".join(intersection)}')
            else:
                if intersection:
                    g.warn(f'We could not find your inputs {list(intersection)} from the following inputs: {g.inputs}')
                g.fallback(command)
        elif all_inputs:
            g.fallback(g.updateCommand)
        elif g.projectName == "settings":
            g.fallback(command)
        else:
            g.fallback(g.updateCommand)

@main.command()
@gauntletParams
@click.argument("tf", nargs = -1, required = False)
@click.option("-a", "--all-tangle-files", is_flag = True, help = "Tangle specified and default files.")
@click.pass_context
def tangle(ctx, gauntlet, tf, all_tangle_files):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(update, gauntlet = g, inputs = [ "settings" ])
        tf = " ".join([ str((g.dir / file).resolve(strict = True)) for file in tf ])
        if all_tangle_files:
            g.run(g.tangleCommand(tf + " " + g.tangle_files))
        else:
            g.run(g.tangleCommand(tf or g.tangle_files))
        checkCommand = f"nix flake check --show-trace {g.dir}"
        if g.run(checkCommand, ignore_stderr = True).returncode > 0:
            ctx.invoke(update, gauntlet = g)
            g.run(checkCommand)
        ctx.invoke(add, gauntlet = g)

@main.command()
@gauntletParams
@click.argument("tf", nargs = -1, required = False)
@click.option("-a", "--all-tangle-files", is_flag = True)
@click.pass_context
def check(ctx, gauntlet, tf, all_tangle_files):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(tangle, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files)

# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786

def tuParams(func):
    @click.option("--tf", multiple = True, default = [])
    @click.option("--all-tangle-files", is_flag = True)
    @click.option("--inputs", multiple = True, default = [])
    @click.option("--all-inputs", is_flag = True)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@main.command(hidden = True)
@gauntletParams
@tuParams
@click.pass_context
def _tu(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(tangle, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files)
        ctx.invoke(update, gauntlet = g, inputs = inputs, all_inputs = all_inputs)

# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786

def exportParams(func):
    @click.option("--ef", multiple = True)
    @click.option("--all-export-files", is_flag = True)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@main.command(name = "export")
@gauntletParams
@tuParams
@click.argument("ef", nargs = -1, required = False)
@click.option("-a", "--all-export-files", is_flag = True, help = "Export specified and default files.")
@click.pass_context
def _export(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs, ef, all_export_files):
    "EF: Export files."
    ef = list(ef)
    kwargs = dict(tf = list(tf) + ef, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, **kwargs)
        ef = [ str((g.dir / file).resolve(strict = True)) for file in (ef + g.opts.export.ef) ]
        if all_export_files:
            g.run(g.nixShell("org-export -f", *ef, *g.export_files, _type = "general"))
        else:
            g.run(g.nixShell("org-export -f", *(ef or g.export_files), _type = "general"))
        ctx.invoke(_tu, gauntlet = g, **kwargs)

@main.command()
@gauntletParams
@tuParams
@click.argument("devshell", required = False)
@click.pass_context
def develop(ctx, devshell, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(f'nix develop --show-trace "{g.dir}#{devshell or "makefile"}"')

@main.command()
@gauntletParams
@tuParams
@click.option("-p", "--pkgs", multiple = True)
@click.option("-P", "--pkg-string")
@click.option("-w", "--with-pkgs", multiple = True)
@click.pass_context
def shell(ctx, gauntlet, pkgs, pkg_string, with_pkgs, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        if pkg_string:
            pass
        elif with_pkgs:
            pkg_string = "(with " + "; with ".join(with_pkgs) + "; [ " + " ".join(pkgs) + " ])"
        else:
            pkg_string = " ".join(pkgs)
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.quickShell(pkg_string))

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def repl(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.nixShell(g.type))

@main.command()
@gauntletParams
@tuParams
@click.option("-p", "--pkgs", multiple = True, default = ("default",))
@click.pass_context
def build(ctx, gauntlet, pkgs, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(f"""nix build --show-trace "{g.dir}#{f'" "{g.dir}#'.join(pkgs)}" """)

@main.command()
@gauntletParams
@tuParams
@click.argument("command")
@click.pass_context
def cmd(ctx, command, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(g.nixShellInDir(escapeQuotes(command)))

@main.command(name = "run", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.option("-s", "--arg-string")
@click.option("-p", "--pkg", default = "default")
@click.pass_context
def _run(ctx, args, gauntlet, arg_string, pkg, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        g.fallback(f"""nix run --show-trace "{g.dir}#{pkg}" -- {arg_string or " ".join(args)}""")

@main.command(name = "touch-test")
@gauntletParams
@tuParams
@click.argument("test")
@click.pass_context
def touch_test(ctx, test, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        test = escapeQuotes(test)
        g.fallback(g.nixShell("touch", test, "&&".type, test))

@main.command()
@gauntletParams
@exportParams
@click.option("--tf", multiple = True, default = [])
@click.option("--all-tangle-files", is_flag = True)
@click.option("-n", "--do-not-push", is_flag = True)
@click.option("-f", "--fds", multiple = True)
@click.option("-e", "--export", is_flag = True)
@click.argument("message", required = False)
@click.pass_context
def quick(ctx, message, gauntlet, fds, tf, all_tangle_files, do_not_push, export, ef, all_export_files):
    kwargs = dict(tf = tf, all_tangle_files = all_tangle_files)
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        if any((ef, all_export_files, export)):
            ctx.invoke(_export, gauntlet = g, ef = ef, all_export_files = all_export_files, **kwargs)
        else:
            ctx.invoke(tangle, gauntlet = g, **kwargs)
        ctx.invoke(push, message = message, fds = fds, gauntlet = g, do_not_push = do_not_push)

@main.command()
@gauntletParams
@tuParams
@exportParams
@click.option("--test/--no-tests", default = True)
@click.option("-n", "--do-not-push", is_flag = True)
@click.option("-f", "--fds", multiple = True)
@click.option("--export/--no-export", is_flag = True, default = True)
@click.argument("message", required = False)
@click.pass_context
def super(
    ctx,
    message,
    gauntlet,
    fds,
    test,
    tf,
    all_tangle_files,
    inputs,
    all_inputs,
    ef,
    all_export_files,
    do_not_push,
    export
):
    kwargs = dict(
        tf = tf,
        all_tangle_files = all_tangle_files,
        inputs = inputs,
        all_inputs = all_inputs,
    )
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        if any((ef, all_export_files, export)):
            ctx.invoke(
                _test if g.doCheck and g.opts.super.test and test else _export,
                gauntlet = g,
                ef = ef,
                all_export_files = all_export_files,
                **kwargs,
            )
        else:
            ctx.invoke(_test if g.doCheck and g.opts.super.test and test else _tu, gauntlet = g, **kwargs)
        ctx.invoke(push, message = message, fds = fds, gauntlet = g, do_not_push = do_not_push)

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def poetry2setup(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        with open(g.dir / "setup.py", "w") as stdout:
            g.fallback(g.nixShellInDir("poetry2setup"), stdout = stdout)

@main.command(name = "touch-tests")
@gauntletParams
@click.pass_context
def touch_tests(ctx, gauntlet):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        g.run(f'find {g.dir}/tests -print | grep -v __pycache__ | xargs touch', stdout = DEVNULL, stderr = DEVNULL, ignore_stderr = True)

@main.command(hidden = True)
@gauntletParams
@tuParams
@click.pass_context
def _tut(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(_tu, gauntlet = g, tf = tf, all_tangle_files = all_tangle_files, inputs = inputs, all_inputs = all_inputs)
        ctx.invoke(touch_tests, gauntlet = g)

@main.command(hidden = True)
@gauntletParams
@tuParams
@exportParams
@click.pass_context
def _tet(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs, ef, all_export_files):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(
            _export,
            gauntlet = g,
            tf = tf,
            all_tangle_files = all_tangle_files,
            inputs = inputs,
            all_inputs = all_inputs,
            ef = ef,
            all_export_files = all_export_files,
        )
        ctx.invoke(touch_tests, gauntlet = g)

@main.command(name = "test")
@gauntletParams
@tuParams
@exportParams
@click.argument("args", nargs = -1, required = False)
@click.option("-e", "--export", is_flag = True)
@click.pass_context
def _test(ctx, args, gauntlet, export, tf, all_tangle_files, inputs, all_inputs, ef, all_export_files):
    kwargs = dict(
        tf = tf,
        all_tangle_files = all_tangle_files,
        inputs = inputs,
        all_inputs = all_inputs,
    )
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        if any((ef, all_export_files, export)):
            ctx.invoke(
                _tet,
                gauntlet = g,
                ef = ef,
                all_export_files = all_export_files,
                **kwargs,
            )
        else:
            ctx.invoke(_tut, gauntlet = g, **kwargs)
        g.fallback(g.test(*args))

@main.command(name = "test-native")
@gauntletParams
@tuParams
@click.argument("args", nargs = -1, required = False)
@click.pass_context
def test_native(ctx, args, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(
            _test,
            "--tb=native" if g.testType == "python" else "",
            args = args,
            gauntlet = g,
            tf = tf,
            all_tangle_files = all_tangle_files,
            inputs = inputs,
            all_inputs = all_inputs,
        )

@main.command()
@gauntletParams
@tuParams
@click.pass_context
def up(ctx, gauntlet, tf, all_tangle_files, inputs, all_inputs):
    for g in (gauntlet,) if gauntlet else (ctx.obj.mkGauntlet(directory = path) for path in ctx.obj.paths):
        ctx.invoke(
            _tu,
            gauntlet = g,
            tf = tf,
            all_tangle_files = all_tangle_files,
            inputs = list(inputs) + [ "titan" "settings" ],
            all_inputs = all_inputs,
        )

if __name__ == "__main__":
    obj=Dict(dict())
    try:
        main(obj=obj)
    finally:
        for g in obj.cls:
            g.run(f"touch {g.dir}/.envrc")
        obj.status.stop()