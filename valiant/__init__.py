#!/usr/bin/env python3

import black

import rich.traceback as RichTraceback

excepthook = RichTraceback.install(show_locals=True)

try:
    import rich_click as click
except ImportError:
    import click

import orjson as json
import re
import sys
import tomllib
from addict import Dict
from colors import strip_color
from ast import literal_eval
from functools import wraps
from itertools import chain
from os import environ
from pathlib import Path
from poetry2setup import build_setup_py
from rich.pretty import pprint
from rich.table import Table
from tempfile import TemporaryDirectory

from valiant.confirm import Confirm
from valiant.gauntlet import Gauntlet as _Gauntlet
from valiant.miscellaneous import *
from valiant.miscellaneous import dirs as mdirs
from valiant.opts import Opts
from valiant.path import SuperPath as SP
from valiant.shell import Shell as _Shell, QuickShell as _QuickShell

from valiant.sh import SH
from sh import ErrorReturnCode, CommandNotFound


@click.group(
    invoke_without_command=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.option("--all/--skip-all", "_all", default=True)
@click.option("--dependencies/--skip-dependencies", default=True)
@click.option("--do-not-prompt", is_flag=True)
@click.option("--export/--skip-export", default=True)
@click.option("--just-export", is_flag=True)
@click.option("--just-tangle", is_flag=True)
@click.option("--just-test", is_flag=True)
@click.option("--just-update", is_flag=True)
@click.option("--offline", is_flag=True)
@click.option("--refresh", is_flag=True)
@click.option("--setup/--skip-setup", default=True)
@click.option("--tangle/--skip-tangle", default=True)
@click.option("--test/--skip-tests", default=True)
@click.option("--update/--skip-update", "_update", default=True)
@click.option("-a", "--all-formats", is_flag=True)
@click.option("-C", "--command-post", multiple=True)
@click.option("-c", "--command-pre", multiple=True)
@click.option("-D", "--dependency", multiple=True)
@click.option("-d", "--dirs", multiple=True)
@click.option("-E", "--working-export-files", multiple=True)
@click.option(
    "-e",
    "--export-files",
    multiple=True,
    callback=lambda ctx, param, value: map(SuperPath, value),
)
@click.option("-F", "--force-with-lease", is_flag=True)
@click.option("-f", "--format", multiple=True)
@click.option("-g", "--do-not-prompt-dependencies", is_flag=True)
@click.option("-G", "--force", is_flag=True)
@click.option("-I", "--all-inputs", is_flag=True)
@click.option("-i", "--inputs", multiple=True)
@click.option("-j", "--ignore-input", multiple=True)
@click.option("-M", "--replace-nix-config")
@click.option("-m", "--replace-nix-opts", multiple=True, type=(str, str))
@click.option("-N", "--nix-config")
@click.option("-n", "--nix-opts", multiple=True, type=(str, str))
@click.option(
    "-o",
    "--opts-dir",
    help="Path to a directory with a global options file.",
    callback=ccaller(SuperPath),
)
@click.option(
    "-O",
    "--opts-file",
    help="Path to a global options file.",
    callback=ccaller(SuperPath),
)
@click.option("-P", "--global-post", multiple=True)
@click.option("-p", "--global-pre", multiple=True)
@click.option("-r", "--remove", multiple=True, help="Remove from flake outputs")
@click.option(
    "-t",
    "--tangle-files",
    multiple=True,
    callback=lambda ctx, param, value: map(SuperPath, value),
)
@click.option("-T", "--working-tangle-files", multiple=True)
@click.option("-v", "--verbose", "verbose", count=True)
@click.pass_context
def main(
    # DO NOT SORT CTX!
    ctx,
    _all,
    _update,
    verbose,
    all_formats,
    all_inputs,
    command_post,
    command_pre,
    dependencies,
    dependency,
    dirs,
    do_not_prompt,
    do_not_prompt_dependencies,
    export_files,
    export,
    force_with_lease,
    force,
    format,
    global_post,
    global_pre,
    ignore_input,
    inputs,
    just_export,
    just_tangle,
    just_test,
    just_update,
    nix_config,
    nix_opts,
    offline,
    opts_dir,
    opts_file,
    refresh,
    remove,
    replace_nix_config,
    replace_nix_opts,
    setup,
    tangle_files,
    tangle,
    test,
    working_export_files,
    working_tangle_files,
):
    ctx.ensure_object(dict)

    if any(h for h in ["-h", "--help"] if h in sys.argv) or (
        ctx.invoked_subcommand in ("remove",)
    ):
        pass
    else:
        ctx.obj.do_not_prompt = do_not_prompt
        ctx.obj.do_not_prompt_dependencies = do_not_prompt_dependencies

        nixArgs = []
        if offline:
            nixArgs.append("--offline")
            configure(stalled_download_timeout=1, connect_timeout=1)
        if refresh:
            nixArgs.append("--refresh")

        global sh

        class sh(SH):
            def __init__(self, *args, **kwargs):
                super().__init__(
                    *args,
                    **(
                        dict(
                            _global_options=dict(_truncate_exc=False),
                            _program_options=Dict(
                                {
                                    prog: (
                                        shBaseOptions.nix_
                                        | dict(
                                            _err=sys.stderr if verbose > 1 else None,
                                        )
                                    )
                                    for prog in nixery
                                }
                            )
                            | dict(
                                nix=shBaseOptions.nix,
                                nix_shell=shBaseOptions.nixShell,
                            ),
                            _program_bakery=Dict(
                                {
                                    prog: dict(kwargs=shBaseKwargs.nix_)
                                    for prog in nixery
                                }
                            )
                            | dict(
                                nix=dict(
                                    kwargs=shBaseKwargs.nix
                                    | (
                                        dict(
                                            offline=True,
                                            connect_timeout=1,
                                        )
                                        if chrooted
                                        else dict()
                                    ),
                                    args=(
                                        "--option",
                                        "stalled-download-timeout",
                                        1,
                                        *nixArgs,
                                    )
                                    if chrooted
                                    else nixArgs,
                                ),
                                nix_shell=dict(kwargs=shBaseKwargs.nixShell),
                            ),
                        )
                        | kwargs
                    ),
                )

            def _print(self, p, **kwargs):
                if verbose > 1:
                    console.log(
                        log_indent + f'Now running "sh" command: {p}', style=style
                    )
                    if options := self._build_kwargs(_options=True, **kwargs):
                        console.log(
                            log_indent + '"sh" command run with the following options:',
                            style=style,
                        )
                        table = Table(title=f'[{style}]"sh" Options', style=style)
                        for column in ("Option", "Value"):
                            table.add_column(column, justify="center")
                        for k, v in options.items():
                            table.add_row(k, str(v))
                        printPadded(table)

        valiantOpts = Opts(name="valiant", sh=sh)

        class SuperPath(SP):
            def _print_in(self):
                log(f"Changing directory from {self.owd} to {self}.")

            def _print_out(self):
                log(f"Changing back from {self} to {self.owd}.")

        class Shell(_Shell):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, sh=sh, **kwargs)

        class QuickShell(_QuickShell):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, sh=sh, **kwargs)

        class Gauntlet(_Gauntlet):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, sh=sh, optsParser=valiantOpts, **kwargs)
                self.shell = Shell(self)
                self.pureshell = Shell(self, pure=True)
                self.quickshell = QuickShell(self)

            def log(self, *args, **kwargs):
                return log(*args, verbose=verbose, **kwargs)

            def notify(self, *args, **kwargs):
                return notify(*args, verbose=verbose, **kwargs)

        offline = offline or chrooted

        opts_dir = (opts_file.parent if opts_file else opts_dir) or local
        ctx.obj.opts = setOpts(
            valiantOpts(
                directory=opts_dir, file=opts_file, all_formats=True, remove=remove
            ),
            opts_dir,
            [] if dirs else [Path.cwd()],
        )

        ctx.obj.skip_all = not _all
        ctx.obj.skip_dependencies = ctx.obj.skip_all or not dependencies
        ctx.obj.skip_setup = ctx.obj.skip_all or not setup
        ctx.obj.skip_export = any(
            (
                not ctx.obj.opts.export.enable,
                ctx.obj.skip_all,
                ctx.obj.skip_setup,
                just_tangle,
                just_test,
                just_update,
                not export,
            )
        )
        ctx.obj.skip_tangle = any(
            (
                not ctx.obj.opts.tangle.enable,
                ctx.obj.skip_all,
                ctx.obj.skip_setup,
                just_export,
                just_test,
                just_update,
                not tangle,
            )
        )
        ctx.obj.skip_tests = any(
            (
                not ctx.obj.opts.test.enable,
                ctx.obj.skip_all,
                ctx.obj.skip_setup,
                just_export,
                just_tangle,
                just_update,
                not test,
            )
        )
        ctx.obj.skip_update = any(
            (
                not ctx.obj.opts["update"].enable,
                ctx.obj.skip_all,
                ctx.obj.skip_setup,
                just_export,
                just_tangle,
                just_test,
                not _update,
            )
        )

        ctx.obj.force = force
        ctx.obj.force_with_lease = force_with_lease
        ctx.obj.inputs = list(inputs)
        ctx.obj.all_inputs = (
            ctx.obj.super_quick_and_update or ctx.obj.quick_and_update or all_inputs
        )
        ctx.obj.ignored_inputs = ignore_input
        ctx.obj.dependencies = dependency

        currentSystemKwargs = dict(impure=True, raw=True, expr="builtins.currentSystem")
        currentSystem = sh.nix.eval(**currentSystemKwargs)
        console.print()
        while not currentSystem:
            warn("Sorry! Couldn't get the current system; trying again...")
            currentSystem = sh.nix.eval(**currentSystemKwargs)
        else:
            log("Current system:", currentSystem)
            ctx.obj.currentSystem = currentSystem

        configure(_config=nix_config, **{opt[0]: opt[1] for opt in nix_opts})
        if replace_nix_config or replace_nix_opts:
            configure(
                _replace=True,
                _config=replace_nix_config,
                **{opt[0]: opt[1] for opt in replace_nix_opts},
            )

        updated_config_text = environ["NIX_CONFIG"]
        updated_config_dict = conf_to_dict(updated_config_text)

        gKwargs = dict(
            currentSystem=ctx.obj.currentSystem,
            export_files=chain(working_export_files, export_files),
            force_with_lease=ctx.obj.force_with_lease,
            force=ctx.obj.force,
            global_post=global_post,
            global_pre=global_pre,
            ignored_inputs=ctx.obj.ignored_inputs,
            skip_export=ctx.obj.skip_export,
            skip_tangle=ctx.obj.skip_tangle,
            skip_tests=ctx.obj.skip_tests,
            skip_update=ctx.obj.skip_update,
            tangle_files=chain(working_tangle_files, tangle_files),
        )

        ctx.obj.gauntlets = dict()
        ctx.obj.dirs = dict()
        dauntlets = {
            d: collectDirs(
                {d: None},
                all_formats=all_formats,
                dependencies=ctx.obj.dependencies,
                formats=format,
                skip_dependencies=ctx.obj.skip_dependencies,
                sh=sh,
                log=log,
                optsParser=valiantOpts,
            )
            for d in map(SuperPath, chain(dirs, ctx.obj.opts.dirs))
        }
        for k, v in dauntlets.items():
            gauntlets = {
                d: Gauntlet(
                    directory=d,
                    opts=update(ctx.obj.opts, g.opts),
                    command_pre=command_pre if d in ctx.obj.dirs else tuple(),
                    command_post=command_post if d in ctx.obj.dirs else tuple(),
                    **gKwargs,
                    **(dict(flake=g.flake) if g.flake else dict(no_flake=True)),
                )
                for d, g in v.items()
            }
            if k in gauntlets:
                ctx.obj.dirs[gauntlets[k]] = gauntlets.values()
            else:
                warn(
                    f"""Sorry; directory {k} is not a valiant project, or doesn't have a ".valiant", "flake.org", or "nix.org" file!"""
                )
            ctx.obj.gauntlets |= gauntlets
        ctx.obj.gauntlets = tuple(ctx.obj.gauntlets.values())


# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786
def gauntletParams(func):
    @click.option("--gauntlet", "_gauntlet", hidden=True)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


@main.command()
@gauntletParams
@click.argument("fds", nargs=-1, required=False, type=click.UNPROCESSED)
@click.pass_context
def add(ctx, fds, _gauntlet):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            flake = g.dir / "flake.nix"
            if flake.exists():
                with TemporaryDirectory() as tmpdir:
                    tmpflake = SuperPath(tmpdir) / "flake.nix"
                    flake.copy(tmpflake)
                    try:
                        output = flake.open("w")
                        with tmpflake.open() as input:
                            for line in input:
                                split = line.split('"')
                                if len(split) > 1:
                                    prefix = split[1].split("/")[0]
                                    prefixIsFile = prefix == "file:"
                                    prefixEndsWithFile = prefix.endswith("file:")
                                    git = sh.git.bake(C=SuperPath(split[1]))
                                    try:
                                        remote = git.remote("get-url", "origin")
                                    except ErrorReturnCode:
                                        pass
                                    else:
                                        if remote.startswith("git@"):
                                            remote = remote.replace(":", "/")
                                            if prefixIsFile:
                                                split[1] = remote.replace(
                                                    "git@", "https://"
                                                )
                                            elif prefixEndsWithFile:
                                                split[1] = remote.replace(
                                                    "git@", "git+https://"
                                                )
                                        else:
                                            if prefixIsFile:
                                                split[1] = remote
                                            elif prefixEndsWithFile:
                                                split[1] = "git+" + remote
                                        line = '"'.join(split)
                                output.write(line)
                    except Exception as e:
                        tmpflake.copy(flake)
                        raise type(e)(e) from e
                    finally:
                        output.close()
            g.add(fds)


@main.command()
@gauntletParams
@click.pass_context
@click.option("-f", "--fds", multiple=True)
@click.argument("message", required=False)
def commit(ctx, message, _gauntlet, fds):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            ctx.invoke(add, fds=fds, _gauntlet=g)
            if g.modified:
                porcelain = fds or [
                    item.split(" ")[-1]
                    for item in g.git.commit(
                        allow_empty_message=True,
                        m='""',
                        dry_run=True,
                        porcelain=True,
                    ).split("\n")
                ]
                g.log_list(
                    porcelain,
                    "Commiting",
                    f"files and directories from {g.dir} to git",
                )
                try:
                    g.git.commit(allow_empty_message=True, m=message or "", _fg=True)
                except ErrorReturnCode:
                    if g.verbose > 2:
                        files = "."
                        af_files = "the above"
                    else:
                        files = g.log_list_format(porcelain)
                        af_files = "the following"
                    warn(
                        f"Could not commit {af_files} files and directories to git{files}"
                    )
                else:
                    g.log_out("Committed", f"files from {g.dir} to git.")


@main.command()
@gauntletParams
@click.option("-f", "--fds", multiple=True)
@click.option("-n", "--do-not-push", is_flag=True)
@click.option("--force", is_flag=True)
@click.option("-F", "--force-with-lease", is_flag=True)
@click.option("-b", "--branch")
@click.option("-r", "--remote", default="origin")
@click.argument("message", required=False)
@click.pass_context
def push(
    ctx, message, _gauntlet, fds, do_not_push, force, force_with_lease, branch, remote
):
    force = force or ctx.obj.force
    force_with_lease = force_with_lease or ctx.obj.force_with_lease
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            if not do_not_push:
                ctx.invoke(commit, message=message, _gauntlet=g, fds=fds)
                if g.modified:
                    current_branch = g.git(
                        "rev-parse", abbrev_ref="HEAD", _long_sep=None
                    )
                    if current_branch == "HEAD":
                        if branch:
                            dest = "HEAD:" + branch
                        else:
                            try:
                                dest = "HEAD:main"
                            except ErrorReturnCode:
                                dest = "HEAD:master"
                    else:
                        dest = branch or current_branch
                    log(
                        f'Pushing repository {g.dir} to the "{dest}" branch of "{remote}"...'
                    )
                    g.git.push(
                        remote,
                        dest,
                        force=force,
                        force_with_lease=force_with_lease,
                        _fg=True,
                    )
                    log(f"Pushed repository {g.dir}.")


@main.command(name="update")
@gauntletParams
@click.argument("inputs", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-a", "--all-inputs", is_flag=True)
@click.option("-i", "--ignore", multiple=True)
@click.pass_context
def _update(ctx, _gauntlet, inputs, all_inputs, ignore):
    if ctx.obj.skip_update:
        if all_inputs or ctx.obj.all_inputs:
            for g in toTuple(_gauntlet or ctx.obj.gauntlets):
                if g.opts["update"].enable:
                    with g.process():
                        ctx.invoke(add, _gauntlet=g)
                        g.updateAll()
    else:
        for g in toTuple(_gauntlet or ctx.obj.gauntlets):
            if g.opts["update"].enable:
                with g.process():
                    ctx.invoke(add, _gauntlet=g)

                    def inner(keys=None):
                        g.update(
                            all_inputs=all_inputs,
                            keys=keys,
                            ignores=ignore,
                        )

                    if inputs or ctx.obj.inputs:
                        inner(chain(inputs, ctx.obj.inputs))
                    else:
                        inner()


@main.command()
@gauntletParams
@click.argument("devshell", required=False)
@click.option("--pure/--impure", default=True)
@click.option("-w", "--with-program", is_flag=True)
@click.pass_context
def develop(ctx, _gauntlet, devshell, pure, with_program):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.process(command=True):
                devShell = devshell or g.opts.devShell or ("makefile-" + g.type)
                expr = normalizeMultiline(
                    f"""

                        let flake = (builtins.getFlake or import) "{g.dir}";
                            inherit (flake.{g.currentSystem}) devShells pkgs;
                        in pkgs.lib.iron.fold.shell pkgs [
                            devShells.{devShell}
                            {f"devShells.{g.projectName}" if with_program else ""}
                            (pkgs.mkShell {{ shellHook = "export PATH=$PATH:{localPath}"; }})
                        ]

                    """
                )
                dwargs = dict(_gauntlet=g, _subcommand="develop")
                if pure:
                    ctx.invoke(deps, expression=expr, shell=True, pure=True, **dwargs)
                    if (
                        ctx.obj.do_not_prompt
                        or (
                            ctx.obj.do_not_prompt_dependencies
                            and (g not in ctx.obj.dirs)
                        )
                        or Confirm.ask(
                            f"Are the dependencies to be built and downloaded for this pure development shell acceptable?",
                            default=False,
                        )
                    ):
                        log(
                            f"""Entering {g.dir}'s pure development shell {devShell}:"""
                        )
                        sh.nix_shell(expr=expr, pure=True, _fg=True)
                else:
                    ctx.invoke(deps, expression=expr, **dwargs)
                    if (
                        ctx.obj.do_not_prompt
                        or (
                            ctx.obj.do_not_prompt_dependencies
                            and (g not in ctx.obj.dirs)
                        )
                        or Confirm.ask(
                            f"Are the dependencies to be built and downloaded for this impure development shell acceptable?",
                            default=False,
                        )
                    ):
                        log(
                            f"""Entering {g.dir}'s impure development shell {devShell}:"""
                        )
                        g.nix.develop(f"{g.dir}#{devShell}", _fg=True)
                log(f"Exited {g.dir}'s devlopment shell.")


# Adapted from: https://github.com/pallets/click/issues/108#issuecomment-280489786
def pkgParams(func):
    @click.option("--pure/--impure", default=True)
    @click.option("-p", "--pkgs", multiple=True)
    @click.option("-P", "--pkg-string", default="")
    @click.option("-w", "--with-pkgs", multiple=True)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


@main.command(name="shell")
@gauntletParams
@pkgParams
@click.argument("command")
@click.pass_context
def _shell(ctx, _gauntlet, pkgs, pkg_string, with_pkgs, pure, command):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.process(command=True):
                # Adapted From:
                # Answer: https://stackoverflow.com/questions/21662474/splitting-a-string-with-brackets-using-regular-expression-in-python/21662493#21662493
                # User: https://stackoverflow.com/users/1903116/thefourtheye
                packages = re.findall(
                    "\((.*?)\)",
                    format_pkg_string(
                        *pkgs, with_pkgs=with_pkgs, pkg_string=pkg_string
                    ),
                )
                quickshell = partial(
                    g.quickshell,
                    *pkgs,
                    pkg_string=pkg_string,
                    with_pkgs=with_pkgs,
                    pure=pure,
                )
                dwargs = dict(_gauntlet=g, _subcommand="shell")
                ctx.invoke(deps, expression=quickshell(return_expr=True), **dwargs)
                if (
                    ctx.obj.do_not_prompt
                    or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                    or Confirm.ask(
                        f"Are the dependencies to be built and downloaded for this temporary shell acceptable?",
                        default=False,
                    )
                ):
                    if command:
                        g.log_list(
                            packages,
                            f"""Running command $'{escapeQuotes(command)}' in a temporary {"" if pure else "im"}pure shell with""",
                            "packages from",
                            g.dir,
                        )
                        with quickshell():
                            sh._run(command, **g.values(), _fg=True)
                        g.log_out(
                            "Finished running command with", f"packages from {g.dir}."
                        )
                    else:
                        g.log_list(
                            packages,
                            f'Entering a temporary {"" if pure else "im"}pure shell with',
                            "packages from",
                            g.dir,
                        )
                        quickshell(context=False)(_fg=True)
                        g.log_out(
                            "Exited temporary shell with", f"packages from {g.dir}."
                        )


@main.command()
@gauntletParams
@click.option("--pure/--impure", default=True)
@click.option("-r", "--repl", "_repl")
@click.pass_context
def repl(ctx, _gauntlet, pure, _repl):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.process(command=True):
                shell = g.pureshell if pure else g.shell
                dwargs = dict(_gauntlet=g, _subcommand="repl")
                ctx.invoke(deps, expression=shell._expression, **dwargs)
                if (
                    ctx.obj.do_not_prompt
                    or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                    or Confirm.ask(
                        f"Are the dependencies to be built and downloaded for this repl acceptable?",
                        default=False,
                    )
                ):
                    with shell:
                        try:
                            log(f"Entering {g.type} repl from {g.dir}:")
                            sh(_repl or g.type)(_fg=True)
                        except (ErrorReturnCode, CommandNotFound):
                            try:
                                log(
                                    f"""Could not enter {g.type} repl from {g.dir}; trying again using the nixpkgs input's "outPath":"""
                                )
                                nixpkgs = sh.nix.eval(
                                    expr=f'((builtins.getFlake or import) "{g.dir}").inputs.nixpkgs.outPath',
                                    **chooseShKwargsOpts("nixEval", sh=sh),
                                )
                                g.nix.run(f"{nixpkgs}#{g.type}", _fg=True)
                            except ErrorReturnCode:
                                log(
                                    f"""Could not enter {g.type} repl using the nixpkgs input's "outPath"; trying again using default package's executable paths..."""
                                )

                                def inner():
                                    log(
                                        f"""Could not enter {g.type} repl from {g.dir}'s {"" if pure else "im"}pure shell; trying to enter through registry:"""
                                    )
                                    g.nix.run(f"nixpkgs#{g.type}", _fg=True)

                                try:
                                    log(
                                        f"Attempting to retrieve the executable paths for {g.dir}'s default package..."
                                    )
                                    drv = Dict(
                                        json.loads(
                                            sh.nix.eval(
                                                expr=normalizeMultiline(
                                                    f"""

                                                        with builtins;
                                                        with ((builtins.getFlake or import)
                                                            "{g.dir}").inputs.nixpkgs.legacyPackages.{g.currentSystem};
                                                        with lib;
                                                        let
                                                            removeNonJSON = obj:
                                                                if (isAttrs obj) then
                                                                    (mapAttrs (n: removeNonJSON) obj)
                                                                else if (isList obj) then
                                                                    (map removeNonJSON obj)
                                                                else
                                                                    obj;
                                                        in toJSON (removeNonJSON
                                                            ((lib.filterAttrs (n: v: elem n [ "meta" "executable" "pname" "name" ])
                                                                {g.type}) // {{
                                                                    passthru.exePath = {g.type}.passthru.exePath or null;
                                                                }}))

                                                    """
                                                ),
                                                **chooseShKwargsOpts("nixEval", sh=sh),
                                            )
                                        )
                                    )
                                    paths = tuple(
                                        chain(
                                            (drv.passthru.exePath,),
                                            map(
                                                drv.meta.get,
                                                (
                                                    "mainprogram",
                                                    "mainProgram",
                                                    "executable",
                                                    "pname",
                                                    "name",
                                                ),
                                            ),
                                        )
                                    )
                                    g.log_list(
                                        paths,
                                        f"The following paths were retrieved",
                                        not_the_following=True,
                                    )
                                    for program in paths:
                                        if program:
                                            log(
                                                f"Entering {g.type} repl through path {program}:"
                                            )
                                            try:
                                                sh(program)(_fg=True)
                                            except ErrorReturnCode:
                                                log(
                                                    f"Could not enter {g.type} repl through {program}; trying a different path..."
                                                )
                                            else:
                                                break
                                        else:
                                            log(
                                                f"Path does not exist; trying a different path..."
                                            )
                                    else:
                                        inner()
                                except ErrorReturnCode:
                                    inner()
                        log(f"Exited {g.type} repl.")


@main.command(name="nix-repl")
@gauntletParams
@click.option("--pure/--impure", default=True)
@click.pass_context
def nix_repl(ctx, _gauntlet, pure):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.process(command=True):
                shell = g.pureshell if pure else g.shell
                dwargs = dict(_gauntlet=g, _subcommand="nix-repl")
                ctx.invoke(deps, expression=shell._expression, **dwargs)
                if (
                    ctx.obj.do_not_prompt
                    or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                    or Confirm.ask(
                        f"Are the dependencies to be built and downloaded for this nix repl acceptable?",
                        default=False,
                    )
                ):
                    with shell:
                        log(f"Entering nix repl in {g.dir}:")
                        g.nix.repl(g.dir, _fg=True)
                        log(f"Exited nix repl in {g.dir}.")


@main.command()
@gauntletParams
@click.argument("pkgs", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-d", "--dry-run", is_flag=True)
@click.pass_context
def build(ctx, _gauntlet, pkgs, dry_run):
    pkgs = pkgs or ("default",)
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            dwargs = dict(_gauntlet=g, _subcommand="build")
            ctx.invoke(deps, pkg=pkgs, **dwargs)
            if (
                ctx.obj.do_not_prompt
                or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                or Confirm.ask(
                    f"Are the dependencies to be built and downloaded for the packages being built acceptable?",
                    default=False,
                )
            ):
                g.log_list(pkgs, "Building", "packages from", g.dir)
                g.nix.build(
                    *(f"{g.dir}#{pkg}" for pkg in pkgs), dry_run=dry_run, _fg=True
                )
                g.log_out("Successfully built", f"packages from {g.dir}.")


@main.command(context_settings=dict(ignore_unknown_options=True), name="nix")
@gauntletParams
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def _nix(ctx, _gauntlet, args):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.dir:
                g.log_list(args, f"Running nix in {g.dir} with", "arguments")
                console.print()
                console.print()
                g.nix(*args, _fg=True)
                console.print()
                console.print()
                g.log_out(f"Successfully ran nix in {g.dir} with", "arguments.")


@main.command(context_settings=dict(ignore_unknown_options=True), name="nix-shell")
@gauntletParams
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def _nix_shell(ctx, _gauntlet, args):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.dir:
                dwargs = dict(_gauntlet=g, _subcommand="nix-shell")
                ctx.invoke(deps, shell=True, args=args, **dwargs)
                if (
                    ctx.obj.do_not_prompt
                    or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                    or Confirm.ask(
                        f"Are the dependencies to be built and downloaded for this nix-shell acceptable?",
                        default=False,
                    )
                ):
                    g.log_list(
                        args, f"Running a nix-shell in {g.dir} with", "arguments"
                    )
                    console.print()
                    console.print()
                    sh.nix_shell(*args, _fg=True)
                    console.print()
                    console.print()
                    g.log_out(
                        f"Successfully ran a nix-shell in {g.dir} with", "arguments."
                    )


@main.command(context_settings=dict(ignore_unknown_options=True), name="nix-run")
@gauntletParams
@click.option("-p", "--pkg", default="default")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def _nix_run(ctx, _gauntlet, pkg, args):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            dwargs = dict(_gauntlet=g, _subcommand="nix-run")
            ctx.invoke(
                deps,
                shell=True,
                expression=f'((builtins.getFlake or import) "{g.dir}").devShells.{g.currentSystem}.{pkg}',
                **dwargs,
            )
            if (
                ctx.obj.do_not_prompt
                or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                or Confirm.ask(
                    f"Are the dependencies to be built and downloaded for this application acceptable?",
                    default=False,
                )
            ):
                g.log_list(
                    args,
                    f"""Running a nix-shell for {"the default package" if pkg == "default" else f'"{pkg}"'} in {g.dir} with""",
                    "arguments",
                )
                console.print()
                console.print()
                g.nix.run(
                    f"{g.dir}#nix-shell-{pkg}", "--", g.dir, "--run", *args, _fg=True
                )
                console.print()
                console.print()
                g.log_out(f"Successfully ran a nix-shell in {g.dir} with", "arguments.")


@main.command()
@gauntletParams
@click.argument("command")
@click.pass_context
def cmd(ctx, command, _gauntlet):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.process(command=True):
                # TODO
                log("")

                sh._run(command, **g, _fg=True)


@main.command(name="run", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@click.argument("args", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-p", "--pkg", default="default")
@click.pass_context
def _run(ctx, args, _gauntlet, pkg):
    """
    ARGS: Arguments to be passed to the program run by `nix run', such as `nix run ".#cat" -- test.txt';
          if the arguments need quotes, use `$'"..."'' in bash, i.e. a dollar sign with two single and double quotes;
          this way, both double quotes and escaped single quotes can be used.
          Eg: `nix run ".#python-"'
    """
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            with g.process(command=True):
                g.log_list(args, f"Running {g.dir}#{pkg} with", "arguments")
                g.nix.run(f"{g.dir}#{pkg}", "--", *args, _fg=True)
                log(f"Successfully ran {g.dir}#{pkg} with", "arguments.")


@main.command()
@gauntletParams
@click.option("-p", "--pkgs", multiple=True, default=("default",))
@click.option("-P", "--priority")
@click.pass_context
def install(ctx, _gauntlet, pkgs, priority):
    for g in toTuple(_gauntlet or ctx.obj.dirs):
        with g.process():
            env_pkg_string = f"' -E 'f: f.packages.{g.currentSystem}.".join(pkgs)
            profile_pkgs = [f"{g.dir}#{pkg}" for pkg in pkgs]

            g.log_list(pkgs, "Installing", "packages from", g.dir)

            # TODO: Ask to remove the pkg and try again?
            try:
                dwargs = dict(_gauntlet=g, _subcommand="install")
                ctx.invoke(deps, pkg=pkgs, **dwargs)
                if (
                    ctx.obj.do_not_prompt
                    or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                    or Confirm.ask(
                        f"Are the dependencies to be built and downloaded for the packages to be installed acceptable?",
                        default=False,
                    )
                ):
                    log('Installing using "nix profile"...')
                    g.nix.profile.install(
                        *profile_pkgs,
                        impure=True,
                        priority=priority or False,
                        _fg=True,
                    )
            except ErrorReturnCode:
                log(
                    'Installation using "nix profile" failed; trying again with "priority = 0"...'
                )
                try:
                    g.nix.profile.install(
                        *profile_pkgs,
                        impure=True,
                        priority=0,
                        _fg=True,
                    )
                except ErrorReturnCode:
                    log(
                        'Installation using "nix profile" with "priority = 0" failed; trying again using "nix-env"...'
                    )
                    sh.nix_env(
                        show_trace=True,
                        f=g.dir,
                        i=True,
                        E=f"f: f.packages.{g.currentSystem}.{env_pkg_string}",
                        _fg=True,
                    )
                    g.log_out(
                        "Successfully installed",
                        "packages from",
                        g.dir,
                        'using "nix-env"!',
                    )
                else:
                    g.log_out(
                        "Successfully installed",
                        "packages from",
                        g.dir,
                        'using "nix profile" with "priority = 0"!',
                    )
            else:
                g.log_out(
                    "Successfully installed",
                    "packages from",
                    g.dir,
                    'using "nix profile"!',
                )


@main.command(name="remove")
@click.argument("pkgs", nargs=-1, type=click.UNPROCESSED)
@click.option("-a", "--all", "_all", is_flag=True)
@click.pass_context
def _remove(ctx, pkgs, _all):
    try:
        profilePackages = sh.nix.profile("list")
    except ErrorReturnCode:
        profilePackages = None
    try:
        envPackages = sh.nix_env(q=True)
    except ErrorReturnCode:
        envPackages = None

    if profilePackages:
        for pkg in pkgs:
            for package in profilePackages.split("\n"):
                package = package.split(" ")[3]
                shortPackage = package.split("-", 1)[1]
                if pkg in shortPackage:

                    def inner():
                        log(f'Removing package "{package}"...')
                        sh.nix.profile("remove", package)
                        log(f'Removed package "{package}"!')

                    if _all:
                        inner()
                    else:
                        if (
                            ctx.obj.do_not_prompt
                            or ctx.obj.do_not_prompt_dependencies
                            or Confirm.ask(
                                f'Would you like to remove the package "{shortPackage}"?',
                                default=False,
                            )
                        ):
                            inner()
    if envPackages:
        for pkg in pkgs:
            for package in envPackages.split("\n"):
                if pkg in package:

                    def inner():
                        log(f'Removing package "{package}"...')
                        sh.nix_env(e=package)
                        log(f'Removed package "{package}"!')

                    if _all:
                        inner()
                    else:
                        if (
                            ctx.obj.do_not_prompt
                            or ctx.obj.do_not_prompt_dependencies
                            or Confirm.ask(
                                f'Would you like to remove the package "{package}"?',
                                default=False,
                            )
                        ):
                            inner()


@main.command(name="touch-test")
@gauntletParams
@click.option("--pure/--impure", default=True)
@click.argument("test")
@click.pass_context
def touch_test(ctx, _gauntlet, test, pure):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            shell = g.pureshell if pure else g.shell
            dwargs = dict(_gauntlet=g, _subcommand="touch-test")
            ctx.invoke(deps, expression=shell._expression, **dwargs)
            if (
                ctx.obj.do_not_prompt
                or (ctx.obj.do_not_prompt_dependencies and (g not in ctx.obj.dirs))
                or Confirm.ask(
                    f"Are the dependencies to be built and downloaded for the tests to be touched acceptable?",
                    default=False,
                )
            ):
                test = SuperPath(test, strict=True)
                log(f"Touching {test}...")
                test.touch(exist_ok=True)
                log(f"Running {test}...")
                with shell:
                    sh(g.type)(test)
                log(f"Test {test} touched and run.")


@main.command()
@gauntletParams
@click.option("-n", "--do-not-push", is_flag=True)
@click.option("-f", "--fds", multiple=True)
@click.option("--force", is_flag=True)
@click.option("-F", "--force-with-lease", is_flag=True)
@click.argument("message", required=False)
@click.pass_context
def quick(ctx, force, force_with_lease, message, _gauntlet, fds, do_not_push):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            if g.modified:
                ctx.invoke(
                    push,
                    force=force,
                    force_with_lease=force_with_lease,
                    message=message,
                    fds=fds,
                    _gauntlet=g,
                    do_not_push=do_not_push,
                )


@main.command(name="super")
@gauntletParams
@click.option("--test/--no-tests", default=True)
@click.option("-n", "--do-not-push", is_flag=True)
@click.option("-f", "--fds", multiple=True)
@click.option("--force", is_flag=True)
@click.option("-F", "--force-with-lease", is_flag=True)
@click.argument("message", required=False)
@click.pass_context
def _super(
    ctx,
    message,
    _gauntlet,
    fds,
    test,
    do_not_push,
    force_with_lease,
    force,
):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            if g.modified:
                if test or g.opts.super.test:
                    ctx.invoke(super_test, _gauntlet=g)
                ctx.invoke(
                    push,
                    force=force,
                    force_with_lease=force_with_lease,
                    message=message,
                    fds=fds,
                    _gauntlet=g,
                    do_not_push=do_not_push,
                )


@main.command()
@gauntletParams
@click.pass_context
def poetry2setup(ctx, _gauntlet):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        pyproject = g.dir / "pyproject.toml"
        if pyproject.exists():
            if Dict(tomllib.loads(pyproject.read_text())).tool.poetry:
                with g.process():
                    log(f"Converting {g.dir}/pyproject.toml to {g.dir}/setup.py...")
                    (g.dir / "setup.py").write_text(
                        # Adapted from:
                        # Answer: https://stackoverflow.com/a/57653328/10827766
                        # User: https://stackoverflow.com/users/5189811/oluwafemi-sule
                        black.format_file_contents(
                            build_setup_py(g.dir), fast=False, mode=black.FileMode()
                        ),
                        newline="\n",
                    )
                    log(f"Converted pyproject.toml to setup.py.")


@main.command(name="touch-tests")
@gauntletParams
@click.pass_context
def touch_tests(ctx, _gauntlet):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            tests = [
                # IMPORTANT: Can't change this `.is_dir()'
                #            as this get files recursively
                f
                for f in (g.dir / "tests").rglob("*")
                if "__pycache__" not in f.parts
            ]
            g.log_list(tests, "Touching", "tests in", g.dir)
            for test in tests:
                test.touch(exist_ok=True)
            log(f"Tests in {g.dir} touched.")


@main.command(name="test", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@click.argument("args", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-f", "--file", multiple=True)
@click.option("-d", "--dirs", is_flag=True)
@click.pass_context
def _test(ctx, args, _gauntlet, file, dirs):
    for g in toTuple(
        _gauntlet
        if _gauntlet
        else (ctx.obj.dirs if file or dirs else ctx.obj.gauntlets)
    ):
        with g.process():
            if g.doCheck and not g.skip_tests:
                ctx.invoke(touch_tests, _gauntlet=g)
                with g.dir:
                    dwargs = dict(_gauntlet=g, _subcommand="test")
                    if g.opts.test:
                        new_deps = g.opts.test.deps.to_dict()
                        new_args = chain(new_deps.pop("args", tuple()), args)
                        ctx.invoke(
                            deps,
                            args=new_args,
                            **new_deps,
                            **dwargs,
                        )
                    else:
                        ctx.invoke(
                            deps,
                            expression=g.pureshell._expression,
                            **dwargs,
                        )
                    if (
                        ctx.obj.do_not_prompt
                        or (
                            ctx.obj.do_not_prompt_dependencies
                            and (g not in ctx.obj.dirs)
                        )
                        or Confirm.ask(
                            f"Are the dependencies to be built and downloaded for the testing process acceptable?",
                            default=False,
                        )
                    ):
                        with g.pureshell:
                            test = g.test(*args, files=file)
                            log(f"Testing {g.dir} with command $'{test}'...")
                            with environment(**g.opts.test.env):
                                test(_fg=True)
                            log(f"All tests in {g.dir} completed successfully!")
            else:
                log(f"Testing for {g.dir} has been skipped!")


@main.command(name="nix-test", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@click.argument("args", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-f", "--file", multiple=True)
@click.option("-d", "--dirs", is_flag=True)
@click.option("-p", "--pkg", default="default")
@click.pass_context
def nix_test(ctx, args, pkg, _gauntlet, file, dirs):
    for g in toTuple(
        _gauntlet
        if _gauntlet
        else (ctx.obj.dirs if file or dirs else ctx.obj.gauntlets)
    ):
        with g.process():
            if g.doCheck and not g.skip_tests:
                ctx.invoke(touch_tests, _gauntlet=g)
                with g.dir:
                    test = partial(g.nix_test, pkg, *args, files=file)
                    dwargs = dict(_gauntlet=g, _subcommand="nix-test")
                    if g.opts.nix_test:
                        new_deps = g.opts.nix_test.deps.to_dict()
                        new_args = chain(new_deps.pop("args", tuple()), args)
                        ctx.invoke(deps, args=new_args, **new_deps, **dwargs)
                    else:
                        ctx.invoke(
                            deps, expression=test(return_expr=True), **dwargs
                        ) if args else ctx.invoke(deps, pkg=(pkg,), **dwargs)
                    if (
                        ctx.obj.do_not_prompt
                        or (
                            ctx.obj.do_not_prompt_dependencies
                            and (g not in ctx.obj.dirs)
                        )
                        or Confirm.ask(
                            f"Are the dependencies to be built and downloaded for the nix testing process acceptable?",
                            default=False,
                        )
                    ):
                        if args or g.opts.nix_test:
                            log(f"Testing {pkg} with command $'{test}'...")
                            with environment(**g.opts.nix_test.env):
                                test()(_fg=True)
                            log(f"All tests for package {pkg} completed successfully!")
                        else:
                            g.nix.build(f"{g.dir}#{pkg}")
            else:
                log(f"Nix testing for {g.dir} has been skipped!")


@main.command(name="super-test", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@click.argument("args", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-f", "--file", multiple=True)
@click.option("-d", "--dirs", is_flag=True)
@click.option("-p", "--pkg", default="default")
@click.pass_context
def super_test(ctx, file, dirs, pkg, args, _gauntlet):
    for g in toTuple(
        _gauntlet
        if _gauntlet
        else (ctx.obj.dirs if file or dirs else ctx.obj.gauntlets)
    ):
        kwargs = dict(args=args, file=file, _gauntlet=g)
        ctx.invoke(_test, **kwargs)
        ctx.invoke(nix_test, pkg=pkg, **kwargs)


@main.command(name="test-native", context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@click.option("-f", "--file", multiple=True)
@click.argument(
    "args", nargs=-1, required=False, type=click.UNPROCESSED, callback=ccaller(list)
)
@click.pass_context
def test_native(ctx, args, _gauntlet, file):
    for g in toTuple(_gauntlet or ctx.obj.gauntlets):
        with g.process():
            ctx.invoke(
                _test,
                args=args + ["--tb=native" if g.group == "python" else ""],
                file=file,
                _gauntlet=g,
            )


@main.command(context_settings=dict(ignore_unknown_options=True))
@gauntletParams
@click.option("--subcommand", "_subcommand", hidden=True)
@click.argument("args", nargs=-1, required=False, type=click.UNPROCESSED)
@click.option("-p", "--pkg", default=("default",), multiple=True)
@click.option("-s", "--shell", is_flag=True)
@click.option("-S", "--store")
@click.option("-P", "--pure", is_flag=True)
@click.option("-r", "--root")
@click.option("-e", "--expression")
@click.option("-d", "--devshell")
@click.option("-I", "--paths", is_flag=True)
@click.option("-t", "--tree", is_flag=True)
@click.option("-D", "--return-dict", is_flag=True)
@click.option("--builds/--only-downloaded", is_flag=True, default=True)
@click.option("--downloads/--only-built", is_flag=True, default=True)
@click.pass_context
def deps(
    ctx,
    args,
    pkg,
    paths,
    builds,
    downloads,
    tree,
    return_dict,
    expression,
    devshell,
    root,
    shell,
    pure,
    store,
    _gauntlet,
    _subcommand,
):
    def get_name(path):
        return path.split("-", 1)[1].removesuffix(".drv")

    def get_path(path):
        return path.split("  ")[1]

    for g in toTuple(_gauntlet or ctx.obj.dirs):
        if _subcommand:
            g.notify(
                f'The following dependencies will be built or downloaded for the "{_subcommand}" command run in {g.dir}:'
            )
        new_shell = shell or g.opts.deps.shell
        new_args = list(chain(args, g.opts.deps.args))
        new_pure = pure or ("--pure" in new_args) or False
        new_pkgs = (f"{root or g.dir}#{p}" for p in pkg)
        expression = expression or (
            f'((builtins.getFlake or import) "{g.dir}").devShells.{g.currentSystem}.{devshell}'
            if devshell
            else None
        )
        # nix-store --query --tree $(nix build --dry-run --json 2> /dev/null | jq -r ".[0].drvPath")
        if tree:
            if new_shell:
                raise click.UsageError(
                    "Using the `shell' option with `tree' is not supported!"
                )
            builder = partial(
                g.nix.build,
                dry_run=True,
                json=True,
                impure=bool(expression),
            )
            parsed_paths = parse_tree(
                sh.nix_store(
                    literal_eval(
                        builder(expr=expression) if expression else builder(*new_pkgs)
                    )[0]["drvPath"],
                    query=True,
                    tree=True,
                    _tty_out=False,
                )
            )
        else:
            kwargs = dict(dry_run=True, _err_to_out=True)
            if new_shell:
                builder = partial(sh.nix_shell, *new_args, pure=new_pure, **kwargs)
            else:
                builder = partial(
                    g.nix.build,
                    impure=bool(expression),
                    **(dict(store=store) if store else dict()),
                    **kwargs,
                )
            output = (
                builder(expr=expression)
                if expression
                else builder()
                if new_shell
                else builder(*new_pkgs)
            ).split("\n")
            built = Table(title=f"[{style}]Packages to be built", style=style)
            built.add_column("Packages")
            downloaded = Table(title=f"[{style}]Packages to be downloaded", style=style)
            downloaded.add_column("Packages")
            switch = None
            for line in output:
                if any_in(
                    line, "derivation will be built:", "derivations will be built:"
                ):
                    switch = 0
                    continue
                if any_in(line, "path will be fetched", "paths will be fetched"):
                    switch = 1
                    continue
                if all(((switch is not None), ("  " in line), (downloads or builds))):
                    line = (get_path if paths else get_name)(strip_color(line.strip()))
                    if switch:
                        if downloads:
                            downloaded.add_row(line)
                    else:
                        if builds:
                            built.add_row(line)
            if builds and built.rows:
                printPadded(built)
            if downloads and downloaded.rows:
                printPadded(downloaded)


@main.command(name="test-click", hidden=True)
@click.pass_context
def test_click(ctx):
    g = next(iter(ctx.obj.gauntlets))


if __name__ == "__main__":
    obj = Dict()
    try:
        main(obj=obj)
    except ErrorReturnCode as e:
        sys.excepthook = excepthook
        sys.tracebacklimit = 0
        raise e from e
    finally:
        for g in obj.cls:
            (g.dir / ".envrc").touch(exist_ok=True)
