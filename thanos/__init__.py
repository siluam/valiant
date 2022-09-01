#!usr/bin/env python3

import click
from addict import Dict
from ast import literal_eval
from collections import namedtuple
from io import TextIOWrapper
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT

output = namedtuple("output", "stdout stderr")

def run(command, stdout = None, stderr = STDOUT, ignore_stderr = False):
    print()
    print(command)
    print()
    command = command.strip()
    p = Popen(command, shell = True, stdout = stdout, stderr = stderr)
    p.wait()
    if p.returncode and not ignore_stderr:
        raise SystemError("Sorry; something happened! Please check the output of the last command run!")
    if stdout:
        return output(
            stdout = TextIOWrapper(p.stdout).read().strip() if p.stdout else None,
            stderr = TextIOWrapper(p.stderr).read().strip() if p.stderr else None,
        )

def get(command, stderr = STDOUT, ignore_stderr = False):
    return run(command, stdout = PIPE, stderr = stderr, ignore_stderr = ignore_stderr)

def escapeQuotes(string):
    return string.replace('"', '\\"').replace("'", "\\'")

class gauntlet:
    def __init__(self, directory):
        self.dir = directory
        self.sir = str(self.dir)
        self.preFiles = " ".join(f"{self.dir}/{file}" for file in ("nix.org", "flake.org", "tests.org", "README.org"))
        self.removeTangleBackups = f"find {self.dir} -name '.\#*.org*' -print | xargs rm &> /dev/null || :"
        self.projectName = self.getPreFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).pname'").stdout.strip('"')
        self.type = self.getPreFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).type'").stdout.strip('"')
        self.files = f"{self.preFiles} {self.dir}/{self.projectName}"
        self.updateCommand = self.fallback(f"nix flake update --show-trace {self.dir}")
        self.inputs = literal_eval(literal_eval(self.getPreFallback(f"""nix eval --show-trace --impure --expr 'with (import {self.dir}); with inputs.nixpkgs.lib; "[ \\"" + (concatStringsSep "\\", \\"" (attrNames inputs)) + "\\" ]"'""").stdout))
        self.currentSystem = self.getPreFallback("nix eval --show-trace --impure --expr builtins.currentSystem").stdout.strip('"')
        self.doCheck = literal_eval(self.getPreFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).packages.{self.currentSystem}.default.doCheck'").stdout.capitalize())
        self.test = self.doCheck or (self.type != "general")

    def fallbackCommand(self, command, files):
        return f"""
            {self.removeTangleBackups}
            {command}
            if [ $? -ne 0 ]; then
                org-tangle -f {files} > /dev/null
                {command}
            fi
        """

    def preFallback(self, command):
        return self.fallbackCommand(command, self.preFiles)

    def getPreFallback(self, command, ignore_stderr = False):
        return get(self.preFallback(command), ignore_stderr = ignore_stderr)

    def nixShell(self, /, _type = None, *args):
        return f"""nix-shell -E '(import {self.dir}).devShells.{self.currentSystem}.makefile-{_type or self.type}' --show-trace --run "{escapeQuotes(' '.join(args))}" """

    def quickShell(self, pkgs):
        return f"""nix-shell -E 'with (import {self.dir}).pkgs.{self.currentSystem}; with lib; mkShell {{ buildInputs = flatten [ " + {pkgs} + " ]; }}' --show-trace"""

    def quickRun(self, pkgs, *args):
        return self.quickShell(pkgs) + f""" --run "{escapeQuotes(' '.join(args))}" """

    def nixShellInDir(self, /, _type = None, *args):
        return self.nixShell("cd", self.dir, "&& (", *args[:-1], args[-1] + ")", _type = _type)

    def quickRunInDir(self, pkgs, *args):
        return self.quickRun(pkgs, "cd", self.dir, "&& (", *args[:-1], args[-1] + ")")

    def fallback(self, command):
        return self.fallbackCommand(command, self.files)

    def tangleCommand(self, files):
        return f"""
            {self.removeTangleBackups}
            {self.nixShell("org-tangle -f", files, _type = "general")}
            if [ $? -ne 0 ]; then
                org-tangle -f {files} > /dev/null
            fi
        """

    def pytest(self, /, _type = None, *args):
        return self.nixShell("pytest", *args, "--suppress-no-test-exit-code", self.dir, _type = _type)

@click.group()
@click.option("-d", "--directory", default = Path.cwd(), type = Path)
@click.pass_context
def main(ctx, directory):
    ctx.ensure_object(dict)
    ctx.obj.cls = gauntlet(directory = directory)

@main.command()
@click.pass_context
def add(ctx):
    run(f"git -C {ctx.obj.cls.dir} add .")

@main.command()
@click.pass_context
def commit(ctx):
    ctx.invoke(add)
    run(f'git -C {ctx.obj.cls.dir} commit --allow-empty-message -am ""')

@main.command()
@click.pass_context
def push(ctx):
    ctx.invoke(commit)
    run(f"git -C {ctx.obj.cls.dir} push")

@main.command()
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def update(ctx, inputs, all_inputs):
    ctx.invoke(add)
    # command = "nix eval --impure --expr 'with (import " + ctx.obj.cls.sir + '); with pkgs.${builtins.currentSystem}.lib; "nix flake lock ' + ctx.obj.cls.sir + """
    #      --update-input ${concatStringsSep " --update-input " (filter (input: ! ((elem input [ "nixos-master" "nixos-unstable" ]) || (hasSuffix "-small" input))) (attrNames inputs))}"' | tr -d '"')
    # """
    inputString = ' --update-input '.join(i for i in ctx.obj.cls.inputs if not ((i in (
        'nixos-master',
        'nixos-unstable',
    )) or i.endswith('-small')))
    command = f"nix flake lock {ctx.obj.cls.dir} --update-input {inputString}"
    if inputs:
        if ("settings" in inputs) and (ctx.obj.cls.projectName == "settings"):
            inputs.remove("settings")
        if inputs and (intersection := set(ctx.obj.cls.inputs).intersection(inputs)):
            run(ctx.obj.cls.fallback(f'nix flake lock {ctx.obj.cls.dir} --show-trace --update-input {"--update-input ".join(intersection)}'))
        else:
            run(command)
    elif all_inputs:
        run(ctx.obj.cls.updateCommand)
    elif ctx.obj.cls.projectName == "settings":
        run(command)
    else:
        run(ctx.obj.cls.updateCommand)

@main.command()
@click.pass_context
def pre_tangle(ctx):
    ctx.invoke(update, inputs = [ "settings" ])
    run(ctx.obj.cls.removeTangleBackups)

@main.command()
@click.option("-F", "--local-files", multiple = True, type = Path)
@click.option("-f", "--tangle-files", multiple = True, type = Path)
@click.option("-a", "--all-files", is_flag = True)
@click.pass_context
def tangle(ctx, local_files, tangle_files, all_files):
    ctx.invoke(pre_tangle)
    local_files = [ (ctx.obj.cls.dir / file) for file in local_files ]
    tangle_files = list(tangle_files)
    if all_files:
        run(ctx.obj.cls.tangleCommand(" ".join(tangle_files + local_files) + " " + ctx.obj.cls.files))
    else:
        run(ctx.obj.cls.tangleCommand(" ".join(tangle_files + local_files) or ctx.obj.cls.files))
    ctx.invoke(add)

@main.command(hidden = True)
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def _tu(ctx, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(tangle, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
    ctx.invoke(update, inputs = inputs, all_inputs = all_inputs)

@main.command()
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.option("-d", "--devshell")
@click.pass_context
def develop(ctx, devshell, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(f'nix develop --show-trace "{ctx.obj.cls.dir}#{devshell or f"makefile-{ctx.obj.cls.type}"}"')

@main.command()
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.option("-p", "--pkgs", multiple = True)
@click.option("-P", "--pkg-string")
@click.option("-w", "--with-pkgs", multiple = True)
@click.pass_context
def shell(ctx, pkgs, pkg_string, with_pkgs, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    if pkg_string:
        pass
    elif with_pkgs:
        pkg_string = "(with " + "; with ".join(with_pkgs) + "; [ " + " ".join(pkgs) + " ])"
    else:
        pkg_string = " ".join(pkgs)
    run(ctx.obj.cls.quickShell(pkg_string))

@main.command()
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def repl(ctx, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(ctx.obj.cls.nixShell(ctx.obj.cls.type))

@main.command()
@click.option("-p", "--pkgs", multiple = True, default = ("default",))
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def build(ctx, pkgs, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(f"""nix build --show-trace "{ctx.obj.cls.dir}#{f'" "{ctx.obj.cls.dir}#'.join(pkgs)}" """)

@main.command()
@click.option("-c", "--command")
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def cmd(ctx, command, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(ctx.obj.cls.nixShellInDir(escapeQuotes(command)))

@main.command(name = "run", context_settings=dict(ignore_unknown_options=True))
@click.argument("args", nargs = -1, required = False)
@click.option("-s", "--arg-string")
@click.option("-p", "--pkg", default = "default")
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def _run(ctx, args, arg_string, pkg, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(f"""nix run --show-trace "{ctx.obj.cls.dir}#{pkg}" -- {arg_string or " ".join(args)}""")

@main.command(name = "touch-test")
@click.argument("test")
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def touch_test(ctx, test, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    test = escapeQuotes(test)
    run(ctx.obj.cls.nixShell("touch", test, "&&", ctx.obj.cls.type, test))

@main.command()
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.pass_context
def quick(ctx, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(tangle, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
    ctx.invoke(push)

@main.command()
@click.option("--test/--no-tests", default = True)
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def super(ctx, test, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tut if ctx.obj.cls.test and test else _tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    ctx.invoke(push)

@main.command()
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def poetry2setup(ctx, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(ctx.obj.cls.nixShellInDir(f"poetry2setup > {ctx.obj.cls.dir}/setup.py"))

@main.command(name = "touch-tests")
@click.pass_context
def touch_tests(ctx):
    run(ctx.obj.cls.nixShellInDir(f'find {ctx.obj.cls.dir}/tests -print | grep -v __pycache__ | xargs touch'), ignore_stderr = True)

@main.command(hidden = True)
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def _tut(ctx, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    ctx.invoke(touch_tests)

@main.command(name = "test")
@click.argument("args", nargs = -1, required = False)
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def _test(ctx, args, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_tut, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(ctx.obj.cls.pytest(*args))

@main.command(name = "test-native")
@click.argument("args", nargs = -1, required = False)
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def test_native(ctx, args, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(_test, "--tb=native", *args, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)

if __name__ == "__main__":
   main(obj=Dict(dict()))
