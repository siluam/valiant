import sh as _sh
import shlex
import weakref

from addict import Dict
from autoslot import SlotsMeta
from pathlib import Path
from rich import print
from rich.pretty import pprint


def filter_options(**options):
    return {
        k: v for k, v in options.items() if k.startswith("_") and not k.startswith("__")
    }


def filter_kwargs(**kwargs):
    return {k: v for k, v in kwargs.items() if not k.startswith("_")}


# Adapted From:
# Answer: https://stackoverflow.com/a/74005838/10827766
# User: https://stackoverflow.com/users/364696/shadowranger
class SHMeta(SlotsMeta):
    def __new__(cls, *args, **kwargs):
        for attr in ("args", "kwargs", "options", "bakery", "baked"):
            setattr(cls, attr, Dict())
        return super().__new__(cls, *args, **kwargs)

    def __getattr__(cls, attr):
        if attr[0].isupper():
            return getattr(_sh, attr)
        else:
            return cls(attr)

    def _format(cls, command, **kwargs):
        return cls(*shlex.split(command.format(**kwargs))) if command else command

    def _run(cls, command, **kwargs):
        return (
            cls._format(command, **kwargs)(**filter_options(**kwargs))
            if command
            else command
        )


class SH(metaclass=SHMeta):
    __slots__ = ("__weakref__",)

    def __init__(
        self,
        prog,
        *args,
        _weakref=None,
        _global_args=tuple(),
        _global_kwargs=None,
        _global_options=None,
        _global_bakery=None,
        _program_args=None,
        _program_kwargs=None,
        _program_options=None,
        _program_bakery=None,
        _reset_global_args=False,
        _reset_global_kwargs=False,
        _reset_global_options=False,
        _reset_global_bakery=False,
        _reset_global=False,
        _reset_program_args=False,
        _reset_program_kwargs=False,
        _reset_program_options=False,
        _reset_program_bakery=False,
        _reset_program=False,
        _reset_all=False,
        **kwargs,
    ):
        kwargs = self._set_args_kwargs_options_bakery(
            _global_args=_global_args,
            _global_kwargs=_global_kwargs,
            _global_options=_global_options,
            _global_bakery=_global_bakery,
            _program_args=_program_args,
            _program_kwargs=_program_kwargs,
            _program_options=_program_options,
            _program_bakery=_program_bakery,
            **kwargs,
        )
        self._reset(
            _all=_reset_all,
            _global_args=_reset_global_args,
            _global_kwargs=_reset_global_kwargs,
            _global_options=_reset_global_options,
            _global_bakery=_reset_global_bakery,
            _global=_reset_global,
            _program_args=_reset_program_args,
            _program_kwargs=_reset_program_kwargs,
            _program_options=_reset_program_options,
            _program_bakery=_reset_program_bakery,
            _program=_reset_program,
        )
        self._args = list(args)
        self._kwargs = filter_kwargs(**kwargs)
        self._options = filter_options(**kwargs)
        if isinstance(prog, (str, bytes, bytearray)):
            self._prog = getattr(_sh, prog)
        else:
            while not isinstance(prog, _sh.Command):
                prog = getattr(prog, "_prog")
            else:
                self._prog = prog
        # TODO: Implement the global version here as well
        self._weakref = _weakref or weakref.ref(self, self)
        name = Path(self._prog._path).name
        if self._weakref not in self.__class__.baked.program[name]:
            bakery = self.__class__.bakery.program[name]
            self._prog = self._prog.bake(
                *bakery.args, **bakery.kwargs, **bakery.options
            )
            if isinstance(self.__class__.baked.program[name], list):
                self.__class__.baked.program[name].append(self._weakref)
            else:
                self.__class__.baked.program[name] = [self._weakref]
            name_underscored = name.replace("-", "_")
            if self._weakref not in self.__class__.baked.program[name_underscored]:
                if isinstance(
                    self.__class__.baked.program[name_underscored],
                    list,
                ):
                    self.__class__.baked.program[name_underscored].append(self._weakref)
                else:
                    self.__class__.baked.program[name_underscored] = [self._weakref]
            name_dashed = name.replace("_", "-")
            if self._weakref not in self.__class__.baked.program[name_dashed]:
                if isinstance(
                    self.__class__.baked.program[name_dashed],
                    list,
                ):
                    self.__class__.baked.program[name_dashed].append(self._weakref)
                else:
                    self.__class__.baked.program[name_dashed] = [self._weakref]

    def _set_args_kwargs_options_bakery(
        self,
        _global_args=tuple(),
        _global_kwargs=None,
        _global_options=None,
        _global_bakery=None,
        _program_args=None,
        _program_kwargs=None,
        _program_options=None,
        _program_bakery=None,
        _processed=False,
        **kwargs,
    ):
        if _global_args and (_global_args != self.__class__.args.world):
            self.__class__.args.world = list(_global_args)
        if _global_kwargs and (_global_kwargs != self.__class__.kwargs.world):
            self.__class__.kwargs.world = _global_kwargs or dict()
        if _global_options and (_global_options != self.__class__.options.world):
            self.__class__.options.world = _global_options or dict()

        # TODO: This doesn't make sense; this needs some way to track every single instance
        #       and if they have been baked with global args, kwargs, and options
        if _global_bakery and (_global_bakery != self.__class__.bakery.world):
            self.__class__.bakery.world = _global_bakery

        if _program_args and (_program_args != self.__class__.args.program):
            _program_args = _program_args or dict()
            self.__class__.args.program = Dict(
                _program_args
                | {k.replace("_", "-"): v for k, v in _program_args.items()}
            )
        if _program_kwargs and (_program_kwargs != self.__class__.kwargs.program):
            _program_kwargs = _program_kwargs or dict()
            self.__class__.kwargs.program = Dict(
                _program_kwargs
                | {k.replace("_", "-"): v for k, v in _program_kwargs.items()}
            )
        if _program_options and (_program_options != self.__class__.options.program):
            _program_options = _program_options or dict()
            self.__class__.options.program = Dict(
                _program_options
                | {k.replace("_", "-"): v for k, v in _program_options.items()}
            )

        if _program_bakery and (_program_bakery != self.__class__.bakery.program):
            _program_bakery = _program_bakery or dict()
            self.__class__.bakery.program = Dict(
                _program_bakery
                | {k.replace("_", "-"): v for k, v in _program_bakery.items()}
                | {k.replace("-", "_"): v for k, v in _program_bakery.items()}
            )

        if kwargs and not _processed:
            return self._set_args_kwargs_options_bakery(_processed=True, **kwargs)
        return kwargs

    def _reset(
        self,
        _all=False,
        _global_args=False,
        _global_kwargs=False,
        _global_options=False,
        _global_bakery=False,
        _global=False,
        _program_args=False,
        _program_kwargs=False,
        _program_options=False,
        _program_bakery=False,
        _program=False,
    ):
        if _global_args or _global or _all:
            self.__class__.args.world = tuple()
        if _global_kwargs or _global or _all:
            self.__class__.kwargs.world = Dict()
        if _global_options or _global or _all:
            self.__class__.options.world = Dict()
        if _global_bakery or _global or _all:
            self.__class__.bakery.world = Dict()
        if _program_args or _program or _all:
            self.__class__.args.program = Dict()
        if _program_kwargs or _program or _all:
            self.__class__.kwargs.program = Dict()
        if _program_options or _program or _all:
            self.__class__.options.program = Dict()
        if _program_bakery or _program or _all:
            self.__class__.bakery.program = Dict()

    def __getattr__(self, attr):
        if len(attr) == 44:
            raise AttributeError
        if attr == "_path":
            try:
                return Path(self._prog._path)
            except TypeError:
                return Path(self._prog._path.decode())
        else:
            prattr = getattr(self._prog, attr)
            if attr.startswith("_"):
                return prattr
            else:
                return self.__class__(
                    prattr,
                    *self._args,
                    _weakref=self._weakref,
                    **self._kwargs,
                    **self._options,
                )

    def bake(self, *args, **kwargs):
        # NOTE: This cannot be changed as it is required to bake cases such as `git -C path'
        p, options = self._build(*args, **kwargs, _baking=True)
        return self.__class__(p, _weakref=self._weakref, **options)

    def _build_args(self, *args, _no_global_args=False, _no_program_args=False):
        _args = list()
        if not _no_global_args:
            _args += self.__class__.args.world
        if not _no_program_args:
            _args += self.__class__.args.program[self._path.name]
        return *_args, *self._args, *args

    def _build_kwargs(
        self,
        _no_global_kwargs=False,
        _no_program_kwargs=False,
        _options=False,
        **kwargs,
    ):
        kwargs = self._set_args_kwargs_options_bakery(**kwargs)
        _kwargs = dict()

        def inner(kw):
            nonlocal _kwargs
            if ("_err" in _kwargs) and ("_err_to_out" in kw):
                del _kwargs["_err"]
            _kwargs |= kw

        if not _no_global_kwargs:
            inner(getattr(self.__class__, "options" if _options else "kwargs").world)
        if not _no_program_kwargs:
            inner(
                getattr(self.__class__, "options" if _options else "kwargs").program[
                    self._path.name
                ]
            )
        if _options:
            inner(self._options)
        else:
            inner(self._kwargs)
        inner(kwargs)
        return _kwargs

    def _build(
        self,
        *args,
        _baking=False,
        _p=None,
        _no_global_args=False,
        _no_global_kwargs=False,
        _no_global_options=False,
        _no_program_args=False,
        _no_program_kwargs=False,
        _no_program_options=False,
        **kwargs,
    ):
        _args = self._build_args(
            *args,
            _no_global_args=_baking or _no_global_args,
            _no_program_args=_baking or _no_program_args,
        )
        _kwargs = self._build_kwargs(
            _no_global_kwargs=_baking or _no_global_kwargs,
            _no_program_kwargs=_baking or _no_program_kwargs,
            **filter_kwargs(**kwargs),
        )
        _options = self._build_kwargs(
            _options=True,
            _no_global_kwargs=_no_global_options,
            _no_program_kwargs=_no_program_options,
            **filter_options(**kwargs),
        )

        p = _p or self._prog
        try:
            p = p.bake(
                *_args,
                **_kwargs,
                **_options,
            )
        except TypeError as e:
            if _options.get("_fg", False):
                _fg = _options.pop("_fg")
                # This is to apply formatting options such as `_long_sep'
                p = p.bake(*_args, **_kwargs, **_options)
                p = p.bake(_fg=_fg)
            else:
                raise TypeError from e
        if _baking:
            return p, _options
        else:
            return p

    def __str__(self):
        return str(self._build())

    def __repr__(self):
        return repr(self._build())

    def __rich_repr__(self):
        yield self.__str__()

    def _print(self, p, **kwargs):
        ...

    def __call__(
        self,
        *args,
        **kwargs,
    ):
        self._print(p := self._build(*args, **kwargs))
        if output := p():
            return output.strip()
