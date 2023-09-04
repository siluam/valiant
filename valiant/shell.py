import sys

from autoslot import Slots
from contextlib import contextmanager
from os import environ, pathsep

from .miscellaneous import (
    filterPath,
    format_pkg_string,
    localPath,
    chooseShKwargsOpts,
    normalizeMultiline,
)
from .sh import SH


class BaseShell(Slots):
    __slots__ = ("_" + attr for attr in ("environ", "pythonpath", "sysPath"))

    def __init__(
        self,
        g,
        pure=False,
        devShell="default",
        sh=SH,
    ):
        self._g = g
        self._pure = pure
        self._pure_prefix = "" if self._pure else "im"
        self._devShell = devShell
        self._nix_shell = sh.nix_shell.bake(**chooseShKwargsOpts("nixShell", sh))
        self._nix_shell_pure = sh.nix_shell.bake(
            **chooseShKwargsOpts("nixShellPure", sh)
        )
        self._expression = normalizeMultiline(
            f"""

                let flake = (builtins.getFlake or import) "{self.dir}";
                    inherit (flake.{self.currentSystem}) devShells pkgs;
                in pkgs.lib.iron.fold.shell pkgs [
                    devShells.{self._devShell}
                    (pkgs.mkShell {{ shellHook = "echo $PATH; exit"; }})
                ]

            """
        )

    def __getattr__(self, attr):
        return getattr(self._g, attr)

    @contextmanager
    def _log(self, exit=False):
        # TODO: Modify this to work under lower verbose levels
        prefix = (
            f"a quick {self._pure_prefix}pure shell in {self.dir}"
            if "quick" in self.__class__.__name__.lower()
            else f"{self.dir}'s {self._pure_prefix}pure shell"
        )
        more_verbose = self.verbose > 2
        self.log_list(
            environ["PATH"].split(":"),
            "Exiting" if exit else "Entering",
            prefix + ("; current $PATH" if more_verbose else ""),
            not_the_following=True,
        )
        if (self.group == "python") and more_verbose:
            self.log_list(
                environ["PYTHONPATH"].split(":"),
                "Current $PYTHONPATH for",
                self.dir,
                not_the_following=True,
            )
            self.log_list(
                sys.path,
                "Current system path for",
                self.dir,
                not_the_following=True,
            )
        yield
        self.log_list(
            environ["PATH"].split(":"),
            "Exited" if exit else "Entered",
            prefix + ("; new $PATH" if more_verbose else ""),
            not_the_following=True,
            sentence_end=".",
        )
        if (self.group == "python") and more_verbose:
            self.log_list(
                environ["PYTHONPATH"].split(":"),
                "New $PYTHONPATH for",
                self.dir,
                not_the_following=True,
            )
            self.log_list(
                sys.path,
                "New system path for",
                self.dir,
                not_the_following=True,
            )

    def __enter__(self):
        with self._log():
            path = filterPath(self._nix_shell_pure(expr=self._expression))

            # TODO
            # self._path = environ["PATH"]
            global environ
            self._environ = environ.copy()

            if self._pure:
                environ["PATH"] = path
                environ["PATH"] += pathsep + str(localPath)
            else:
                environ["PATH"] += pathsep + path

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        with self._log(exit=True):
            # TODO
            # environ["PATH"] = self._path
            global environ
            environ.update(self._environ)


class QuickShell(BaseShell):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # Adapted from:
    # Answer: https://stackoverflow.com/a/10252925/10827766
    # User: https://stackoverflow.com/users/1347411/jonathan-d-lettvin
    def __call__(
        self,
        *pkgs,
        with_pkgs=tuple(),
        pkg_string="",
        pure=True,
        context=True,
        return_expr=False,
    ):
        expr = normalizeMultiline(
            f"""

                with ((builtins.getFlake or import) "{self.dir}").pkgs.{self.currentSystem};
                with lib;
                mkShell {{
                    buildInputs = flatten [
                        {format_pkg_string(*pkgs, with_pkgs=with_pkgs, pkg_string=pkg_string)}
                    ];
                    {'shellHook = "echo $PATH; exit";' if context else ""}
                }}

            """
        )
        if return_expr:
            return expr
        else:
            with self._log():
                self._pure = pure
                devShell = getattr(
                    self, "_" + ("nix_shell_pure" if self._pure else "nix_shell")
                ).bake(expr=expr)
                if context:
                    self.devShell = devShell
                    return self
                else:
                    return devShell

    def __enter__(self):
        path = filterPath(self.devShell())

        # TODO
        # self._path = environ["PATH"]
        global environ
        self._environ = environ.copy()

        if self._pure:
            environ["PATH"] = path
            environ["PATH"] += pathsep + str(localPath)
        else:
            environ["PATH"] += pathsep + path

        return self


class Shell(BaseShell):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._expression = f'((builtins.getFlake or import) "{self.dir}").devShells.{self.currentSystem}.makefile-{self.type}-pythonpath'

    def __enter__(self):
        with self._log():
            path = filterPath(
                self._nix_shell_pure(
                    expr=f'((builtins.getFlake or import) "{self.dir}").devShells.{self.currentSystem}.makefile-{self.type}-path'
                )
            )

            # TODO
            # self._path = environ["PATH"]
            global environ
            self._environ = environ.copy()

            if self._pure:
                environ["PATH"] = path
                environ["PATH"] += pathsep + str(localPath)
            else:
                environ["PATH"] += pathsep + path

            if self.group == "python":
                pythonpath = filterPath(self._nix_shell_pure(expr=self._expression))
                self._pythonpath = environ["PYTHONPATH"]
                self._sysPath = sys.path
                if self._pure:
                    environ["PYTHONPATH"] = pythonpath
                    sys.path = []
                else:
                    environ["PYTHONPATH"] += pathsep + pythonpath
                for path in pythonpath.split(":"):
                    sys.path.append(path)

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        with self._log(exit=True):
            # TODO
            # environ["PATH"] = self._path
            global environ
            environ.update(self._environ)

            if self.group == "python":
                # TODO
                # environ["PYTHONPATH"] = self._pythonpath

                sys.path = self._sysPath
