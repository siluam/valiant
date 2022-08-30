#!usr/bin/env python3

import click
from addict import Dict
from collections import namedtuple
from io import TextIOWrapper
from pathlib import Path
from subprocess import Popen, PIPE

output = namedtuple("output", "stdout stderr returncode")

def run(command, stdout = PIPE):
    p = Popen(command, shell = True, stdout = stdout, stderr = PIPE)
    p.wait()
    if stdout:
        return output(TextIOWrapper(p.stdout).read(), TextIOWrapper(p.stderr).read(), p.returncode)

class gauntlet:
    def __init__(self, directory):
        self.dir = directory
        self.sir = str(self.dir)
        self.preFiles = " ".join(f"{self.dir}/{file}" for file in ("nix.org", "flake.org", "tests.org", "README.org"))
        self.removeTangleBackups = f"find {self.dir} -name '.\#*.org*' -print | xargs rm &> /dev/null || :"
        self.projectName = run(self.preFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).pname")).stdout
        self.type = run(self.preFallback(f"nix eval --show-trace --impure --expr '(import {self.dir}).type")).stdout
        self.files = f"{self.preFiles} {self.dir}/{self.projectName}"
        self.updateCommand = self.fallback(f"nix flake update --show-trace {self.dir}")

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

    def nixShell(self, _type):
        return "nix-shell -E '(import $(realfileDir)).devShells.${builtins.currentSystem}.makefile-" + _type + "' --show-trace --run"

    def quickShell(self, pkgs):
        return "nix-shell -E 'with (import $(realfileDir)).pkgs.${builtins.currentSystem}; with lib; mkShell { buildInputs = flatten [ " + pkgs + " ]; }' --show-trace"

    def fallback(self, command):
        return self.fallbackCommand(command, self.files)

    def tangleCommand(self, files):
        return f"""
            {self.removeTangleBackups}
            {self.nixShell("general")}
            if [ $? -ne 0 ]; then
                org-tangle -f {files} > /dev/null
            fi
        """

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
    command = "nix eval --impure --expr 'with (import " + ctx.obj.cls.sir + '); with pkgs.${builtins.currentSystem}.lib; "nix flake lock ' + ctx.obj.cls.sir + """
         --update-input ${concatStringsSep " --update-input " (filter (input: ! ((elem input [ "nixos-master" "nixos-unstable" ]) || (hasSuffix "-small" input))) (attrNames inputs))}"' | tr -d '"')
    """
    if inputs:
        if ("settings" in inputs) and (ctx.obj.cls.projectName == "settings"):
            inputs.remove("settings")
        if inputs:
            return ctx.obj.cls.fallback(f'nix flake lock {ctx.obj.cls.dir} --show-trace --update-input {"--update-input ".join(inputs)}')
        else:
            return command
    elif all_inputs:
        return ctx.obj.cls.updateCommand
    elif ctx.obj.cls.projectName == "settings":
        return command
    else:
        return ctx.obj.cls.updateCommand

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
        run(ctx.obj.cls.tangleCommand(" ".join(tangle_files + local_files) if (tangle_files or local_files) else ctx.obj.cls.files))
    ctx.invoke(add)

@main.command(hidden = True)
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def tu(ctx, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(tangle, local_files = local_files, tangle_files = tangle_files, all_files = all_files)
    ctx.invoke(update, inputs = inputs, all_inputs = all_inputs)

@main.command()
@click.option("-d", "--devshell")
@click.option("-F", "--local-files", multiple = True, default = [])
@click.option("-f", "--tangle-files", multiple = True, default = [])
@click.option("-A", "--all-files", is_flag = True)
@click.option("-i", "--inputs", multiple = True)
@click.option("-a", "--all-inputs", is_flag = True)
@click.pass_context
def develop(ctx, devshell, local_files, tangle_files, all_files, inputs, all_inputs):
    ctx.invoke(tu, local_files = local_files, tangle_files = tangle_files, all_files = all_files, inputs = inputs, all_inputs = all_inputs)
    run(f'nix develop --show-trace "{ctx.obj.cls.dir}#{devshell or f"makefile-{ctx.obj.cls.type}"}"', stdout = None)

if __name__ == "__main__":
   main(obj=Dict(dict()))
