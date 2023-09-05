import black
import orjson as json

from addict import Dict
from autoslot import Slots
from contextlib import contextmanager
from itertools import chain
from more_itertools import intersperse
from os import chdir
from pathlib import Path
from rich.console import Console
from rich.table import Table
from sh import ErrorReturnCode

from .miscellaneous import *
from .path import SuperPath
from .sh import SH
from .shell import QuickShell, Shell


class Gauntlet(Slots):
    def __init__(
        self,
        directory,
        *,
        all_inputs=False,
        command_post=tuple(),
        command_pre=tuple(),
        currentSystem="x86_64-linux",
        export_files=tuple(),
        flake=None,
        no_flake=False,
        force=False,
        force_with_lease=False,
        global_post=tuple(),
        global_pre=tuple(),
        ignored_inputs=tuple(),
        opts=None,
        optsParser=None,
        remove=tuple(),
        sh=SH,
        skip_export=False,
        skip_tangle=False,
        skip_tests=False,
        skip_update=False,
        tangle_files=tuple(),
        verbose=0,
    ):
        self.list_delimiter = "\n\t\t"

        self.no_flake = no_flake

        self.dir = SuperPath(directory)
        self.sir = str(self.dir)

        console.print()
        self.log(f"Initializing the Gauntlet for {self.dir}...")

        self.remove = remove
        self.opts = setOpts(
            opts
            or (
                optsParser(directory=self.dir, all_formats=True, remove=self.remove)
                if optsParser
                else Dict()
            ),
            self.dir,
            [],
        )
        self.opts.format = Dict(
            {
                k: v | dict(ignore=[SuperPath(self.dir, file) for file in v.ignore])
                for k, v in self.opts.format.items()
            }
        )

        self.verbose = verbose or self.opts.verbose or 0

        self.command_pre = command_pre or self.opts.command_pre
        self.global_pre = global_pre or self.opts.global_pre
        self.command_post = command_post or self.opts.command_post
        self.global_post = global_post or self.opts.global_post

        self.skip_export = skip_export or not self.opts.export.enable
        self.skip_tangle = skip_tangle or not self.opts.tangle.enable
        self.skip_tests = skip_tests or not self.opts.test.enable
        self.skip_update = skip_update or not self.opts["update"].enable

        self.sh = sh

        orgKwargs = dict(debug=verbose, force=True, use_nix_path=True)
        self.org_export = self.sh.org_export.bake(**orgKwargs)
        self.org_tangle = self.sh.org_tangle.bake(**orgKwargs)

        self.git = self.sh.git.bake(C=self.dir)

        self.nix = (
            self.sh.nix.bake(**shKwargs.nix, **shOptions.nix)
            if sh == SH
            else self.sh.nix
        )

        self.all_inputs = all_inputs or not (self.dir / "flake.lock").exists()
        self.ignored_inputs = ignored_inputs
        self.updateAll = self.nix.flake.update.bake(self.dir)

        self.currentSystem = currentSystem
        self.force = force
        self.force_with_lease = force_with_lease
        self.global_pre_post_run = False

        if self.skip_tangle:
            self.pre_tangle_files = self.tangle_files = tuple()
        else:
            self.pre_tangle_files = set(
                (
                    SuperPath(self.dir, file)
                    for file in chain(
                        (
                            "README.org",
                            "nix.org",
                            "flake.org",
                            "tests.org",
                            "index.org",
                        ),
                        self.opts.tangle.tangle_files,
                        tangle_files,
                    )
                )
            )
            self.tangle(self.pre_tangle_files)

        if not (self.skip_update or self.no_flake):
            if (lockfile := self.dir / "flake.lock").exists():
                self.inputs = Dict(
                    json.loads(lockfile.read_text())
                ).nodes.root.inputs.keys()
                self.update()
            else:
                self.update(all_inputs=True)
                self.inputs = Dict(
                    json.loads(lockfile.read_text())
                ).nodes.root.inputs.keys()

        self.default_flake = Dict(
            pname=self.dir.name,
            type="general",
            group="general",
            doCheck=False,
            testFiles=None,
        )
        if self.no_flake:
            self.flake = self.default_flake
        else:
            self.flake = flake or getFlake(
                sh=self.sh,
                directory=self.dir,
            )

        table = Table(title=f"[{style}]Ensured Variables", style=style)
        for column in ("Name", "Value"):
            table.add_column(column, justify="center")

        self.log("Setting ensured variables...")

        if self.skip_tests:
            self.projectName = self.default_flake.pname
            for attr in ("type", "doCheck", "group", "testFiles"):
                setattr(self, attr, self.default_flake[attr])
        else:
            self.projectName = self.flake.pname
            self.type = self.flake.type
            self.group = self.flake.group
            self.doCheck = self.flake.doCheck
            self.testFiles = self.flake.testFiles or (
                (self.projectName,) if self.group == "emacs" else None
            )

        self.shell = Shell(self)
        self.pureshell = Shell(self, pure=True)
        self.quickshell = QuickShell(self)

        variables = {
            "projectName": "Project Name",
            "type": "Type",
            "group": "Group",
            "testFiles": "Test Files",
            "doCheck": "Do Check",
        }
        for k, v in variables.items():
            table.add_row(v, str(getattr(self, k)))

        console.print()
        printPadded(table)

        if self.doCheck and (not self.skip_tests):
            self.notify(
                f"Testing has been enabled, as the group is [{log_style_mimic}]{self.group}[/{log_style_mimic}], and the `doCheck` value is [{log_style_mimic}]{self.doCheck}[/{log_style_mimic}]!",
            )
        else:
            console.print()

        if not self.skip_tangle:
            additional_tangle_files = [
                SuperPath(self.dir, file) for file in (self.projectName,)
            ]
            self.tangle_files = set(
                chain(
                    self.pre_tangle_files,
                    additional_tangle_files,
                )
            )
            self.tangle(additional_tangle_files)

        self.sh.nixfmt(*self.excluded_parts("nix"), quiet=True, _ok_code=(0, 1))
        self.sh.black(*self.excluded_parts("py"), quiet=True, _ok_code=(0, 1, 123))

        if self.skip_export:
            self.export_files = tuple()
        else:
            # NOTE: Some files here may depend on previous files during export.
            # Adapted from:
            # Answer: https://stackoverflow.com/a/17016257/10827766
            # User: https://stackoverflow.com/users/1219006/jamylak
            self.export_files = tuple(
                dict.fromkeys(
                    SuperPath(self.dir, file)
                    for file in chain(
                        ("index.org",),
                        self.opts.export.export_files,
                        export_files,
                    )
                )
            )
            self.export(self.export_files)

        if self.verbose > 2:
            self.log("Gauntlet Initialized:\n", self)
        else:
            self.log(f"Gauntlet for {self.dir} initialized!")
        console.print("\n")

    def excluded_parts(self, ext):
        return (
            str(file)
            for file in self.dir.rglob("*." + ext)
            if not (
                any(
                    p
                    for p in (
                        "directory_templates",
                        "dt",
                    )
                    if p in file.parts
                )
                or file in self.opts.format[ext].ignore
            )
        )

    def log(self, *args, **kwargs):
        ...

    def notify(self, *args, **kwargs):
        ...

    def values(self):
        # return {item: getattr(self, item) for item in self.__slots__}
        return dirs(self)

    def __rich_repr__(self):
        for k, v in (
            {
                item: getattr(self, item)
                for item in set(
                    getFuncDefaults(self.__class__).defaults.keys()
                ).intersection(set(self.__slots__))
                if item not in ("flake",)
            }
            | dict(
                directory=self.dir,
            )
        ).items():
            yield k, v

    def repr_format(self, v):
        console = f"Console(log_path = {log_path}, log_time = {log_time})"
        match v:
            case t if isinstance(t, str):
                return f"""'''{v}'''"""
            case t if isinstance(t, Console):
                return console
            case t if isinstance(t, SuperPath):
                return f'SuperPath("{v}")'
            case t if isinstance(t, Path):
                return f'Path("{v}")'
            case t if isinstance(t, self.sh.Command):
                program, args = str(v).split(" ", 1)
                return f"""Command("{program}").bake('''{args}''')"""
            case _:
                return v

    def __repr__(self):
        values = dict()
        for k, v in (
            {
                item: getattr(self, item)
                for item in set(getFuncDefaults(Gauntlet).defaults.keys()).intersection(
                    set(self.__slots__)
                )
                if item not in ("flake",)
            }
            | dict(
                directory=self.dir,
            )
        ).items():
            values[k] = self.repr_format(v)
        return self.list_delimiter.join(
            black.format_file_contents(
                # Adapted from:
                # Answer: https://stackoverflow.com/a/62943073/10827766
                # User: https://stackoverflow.com/users/11978207/nvkr
                f"Gauntlet(\n"
                + "\n".join(
                    f"{k} = {v}," for k, v in dict(sorted(values.items())).items()
                )
                + "\n)",
                fast=False,
                mode=black.FileMode(),
            ).split("\n")
        )

    def __eq__(self, directory):
        return directory in (self.dir, self.sir)

    def __hash__(self):
        return hash(self.dir)

    def log_list_format(self, items):
        return ":" + self.list_delimiter + self.list_delimiter.join(map(str, items))

    def log_list(self, items, *args, not_the_following=False, sentence_end="..."):
        args = [str(arg) for arg in args if arg != ""]
        if self.verbose > 2:
            if not not_the_following:
                args.insert(1, "the following")
            suffix = args[-1] + self.log_list_format(items)
        else:
            suffix = args[-1] + sentence_end
        if len(args) == 1:
            self.log(suffix)
        elif len(args) == 2:
            self.log(args[0], suffix)
        else:
            self.log(*args[0:-2], suffix)

    def log_out(self, *args):
        args = [str(arg) for arg in args if arg != ""]
        if self.verbose > 2:
            args.insert(1, "the above")
        self.log(*args)

    @contextmanager
    def withDir(self, d):
        chdir(d)
        yield
        chdir(self.dir)

    @contextmanager
    def holdTangle(self, export_files):
        if self.skip_tangle:
            yield
        else:
            tangle_files = self.tangle_files
            self.tangle_files |= {
                SuperPath(self.dir, fd, strict=True) for fd in export_files
            }
            yield
            self.tangle_files = tangle_files

    @contextmanager
    def process(self, command=False):
        with configuring(
            _replace=self.opts.nix.config.replace,
            _config=self.opts.nix.config.text,
            _file=self.opts.nix.config.file,
            **self.opts.nix.config.opts,
        ):

            def runCmds(p):
                for cmd in p:
                    if cmd.startswith("org-tangle"):
                        cmd = cmd.replace(
                            "org-tangle",
                            " ".join(
                                (
                                    "org-tangle",
                                    "-d" if self.verbose else "",
                                    "-use-nix-path",
                                )
                            ),
                        )
                    self.sh._run(cmd, **self.values(), _fg=True)

            pre = self.command_pre if command else self.global_pre
            post = self.command_post if command else self.global_post

            if command:
                runCmds(pre)
                yield
                runCmds(post)
            else:
                if self.global_pre_post_run:
                    yield
                else:
                    self.global_pre_post_run = True
                    runCmds(pre)
                    yield
                    runCmds(post)

    def add(self, fds=tuple()):
        if fds:
            self.log_list(
                fds,
                "Adding",
                f"files from {self.dir} to git",
            )
        else:
            self.log(f"Adding all files from {self.dir} to git...")
            fds = (".",)
        if self.modified:
            self.git.add(*fds)
        self.log_out("The", f"files from {self.dir} were added.")

    def removeTangleBackups(self):
        for file in set(chain.from_iterable(map(self.dir.rglob, ("*.*~", "#*.org*")))):
            file.unlink()

    def tangle(self, files, exporting=False):
        after_exporting = " after exporting" if exporting else ""
        self.log_list(
            files,
            "Now tangling",
            "files and directories from " + self.sir + after_exporting,
        )
        self.removeTangleBackups()
        self.org_tangle(*files)
        self.add()
        self.log_out(
            "Tangled",
            "files from " + self.sir + after_exporting,
        )

    def tangleFiles(self, files=tuple()):
        self.tangle(chain(files, self.tangle_files))

    def export(self, files):
        self.log_list(files, "Now exporting", "files from", self.dir)
        self.org_export(*files)
        self.log_out("Exported", "files from", self.sir + ".")
        self.tangle(files, exporting=True)

    def mkInputs(self, keys=tuple(), ignores=tuple()):
        return ["--update-input"] + list(
            intersperse(
                "--update-input",
                (
                    i
                    for i in (keys or self.inputs)
                    if not (
                        any(
                            map(
                                i.endswith,
                                (
                                    "-unstable",
                                    "-master",
                                    "-small",
                                ),
                            )
                        )
                        or (
                            i
                            in chain(
                                self.opts["update"].ignore, self.ignored_inputs, ignores
                            )
                        )
                    )
                ),
            )
        )

    def mkUpdateCommand(self, all_inputs=False, keys=tuple(), ignores=tuple()):
        if all_inputs or self.all_inputs:
            self.log(f"Now updating all inputs from {self.dir}/flake.nix...")
            return self.updateAll
        else:
            inputs = self.mkInputs(keys=keys, ignores=ignores)
            self.log_list(
                (
                    # NOTE: Taken from searching for "repr.path"
                    #       in the output of `nix-shell -p python3Packages.rich --run "python -m rich.theme"'
                    f"[magenta]{item}[/magenta]"
                    for item in inputs
                    if item != "--update-input"
                ),
                "Now updating",
                f"inputs from {self.dir}/flake.nix",
            )
            return self.nix.flake.lock.bake(self.dir, *inputs)

    def update(self, all_inputs=False, keys=tuple(), ignores=tuple()):
        try:
            self.mkUpdateCommand(all_inputs=all_inputs, keys=keys, ignores=ignores)()
        except ErrorReturnCode:
            self.mkUpdateCommand(all_inputs=True)
        self.log_out("Updated", f"inputs from {self.dir}/flake.nix.")

    @property
    def modified(self):
        if self.force or self.force_with_lease:
            return True
        status = self.git.status()
        while not status:
            status = self.git.status()
        return any_in(status, "Your branch is ahead of", "HEAD detached from") or (
            "nothing to commit, working tree clean" not in status
        )

    def nix_test(self, pkg, *args, files=tuple(), return_expr=False):
        if self.opts.nix_test.cmd:
            return self.sh._format(self.opts.nix_test.cmd, **self.values())
        else:
            args = chain(args, self.opts.test.args)
            match self.group:
                case "python":
                    program = self.opts.test.program or "pytest"
                    ft = files or ("./.",)
                    if program == "pytest":
                        expr = normalizeMultiline(
                            f"""

                                (builtins.getFlake or import "{self.dir}").pkgs.${{
                                  builtins.currentSystem
                                }}.python3Packages.{pkg}.overridePythonAttrs (old: {{
                                  pytestFlagsArray = (old.pytestFlagsArray or [ ]) ++ [
                                    "{'" "'.join(chain(args, ft))}"
                                  ];
                                }})

                            """
                        )
                        if return_expr:
                            return expr
                        return self.sh.nix.build.bake(
                            impure=True,
                            expr=expr,
                        )
                    else:
                        ...
                case "emacs":
                    ...
                case _:
                    ...

    def test(self, *args, files=tuple()):
        if self.opts.test.cmd:
            return self.sh._format(self.opts.test.cmd, **self.values())
        else:
            args = chain(args, self.opts.test.args)
            match self.group:
                case "python":
                    program = self.opts.test.program or "pytest"
                    if files:
                        ft = []
                        for file in files:
                            split_file = file.partition("::")
                            ft.append(
                                str(SuperPath(split_file[0], strict=True))
                                + "".join(split_file[1:])
                            )
                    else:
                        ft = (
                            SuperPath(self.dir, d)
                            for d in (files or self.opts.test.dirs)
                        ) or (self.dir,)
                    if program == "pytest":
                        opts = dict(suppress_no_test_exit_code=True)
                        if self.flake.parallel:
                            opts |= dict(dist="loadgroup", n="auto")
                    else:
                        opts = dict()
                    return self.sh(
                        program,
                        *args,
                        *ft,
                        **opts,
                    )
                case "emacs":
                    return self.sh.emacs.bake(
                        *args,
                        batch=True,
                        eval="\"(progn (require '"
                        + ") (require '".join(self.testFiles)
                        + '))"',
                    )
                case _:
                    return self.sh(*args)
