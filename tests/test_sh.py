from addict import Dict
from pytest import fixture
from shutil import which
from valiant import SH


class TestSH:
    @fixture
    def _git(self):
        return which("git")

    @fixture
    def _nix(self):
        return which("nix")

    def test_bake(self, _git):
        try:
            git = SH.git.bake(C="path")
            assert str(git) == f"{_git} -C path"
        finally:
            git._reset(_all=True)

    def test_global_args(self, _git, _nix):
        try:
            git = SH.git.bake(_global_args=("help",))
            assert str(git) == f"{_git} help"
            assert str(SH.nix) == f"{_nix} help"
        finally:
            git._reset(_all=True)

    def test_global_kwargs(self, _git, _nix):
        try:
            git = SH.git.bake(_global_kwargs=dict(help=True))
            assert str(git) == f"{_git} --help"
            assert str(SH.nix) == f"{_nix} --help"
        finally:
            git._reset(_all=True)

    def test_program_args(self, _git, _nix):
        try:
            git = SH.git.bake(
                _program_args=dict(
                    nix=("help",),
                )
            )
            assert str(git) == _git
            assert str(SH.nix) == f"{_nix} help"
        finally:
            git._reset(_all=True)

    def test_program_kwargs(self, _git, _nix):
        try:
            git_opts = Dict()
            git_opts._program_kwargs.nix.help = True
            git = SH.git.bake(**git_opts)
            assert str(git) == _git
            assert str(SH.nix) == f"{_nix} --help"
        finally:
            git._reset(_all=True)
