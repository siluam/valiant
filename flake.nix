{
  nixConfig = {
    # Adapted From: https://github.com/divnix/digga/blob/main/examples/devos/flake.nix#L4
    accept-flake-config = true;
    auto-optimise-store = true;
    builders-use-substitutes = true;
    cores = 0;
    extra-experimental-features =
      "nix-command flakes impure-derivations recursive-nix";
    fallback = true;
    flake-registry =
      "https://raw.githubusercontent.com/syvlorg/flake-registry/master/flake-registry.json";
    keep-derivations = true;
    keep-outputs = true;
    max-free = 1073741824;
    min-free = 262144000;
    show-trace = true;
    trusted-public-keys = [
      "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "nickel.cachix.org-1:ABoCOGpTJbAum7U6c+04VbjvLxG9f0gJP5kYihRRdQs="
      "sylvorg.cachix.org-1:xd1jb7cDkzX+D+Wqt6TemzkJH9u9esXEFu1yaR9p8H8="
    ];
    trusted-substituters = [
      "https://cache.nixos.org/"
      "https://nix-community.cachix.org"
      "https://nickel.cachix.org"
      "https://sylvorg.cachix.org"
    ];
    warn-dirty = false;
  };
  description = "Fine. I'll do it myself.";
  inputs = rec {
    flake-utils.url = "github:numtide/flake-utils";
    flake-utils-plus.url = "github:gytis-ivaskevicius/flake-utils-plus";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
    nixpkgs.url = "github:nixos/nixpkgs/nixos-23.05";
    poetry2setup = {
      url = "github:syvlorg/poetry2setup";
      flake = false;
    };
    click-aliases = {
      url = "github:click-contrib/click-aliases";
      flake = false;
    };
    pytest-hy = {
      url = "github:syvlorg/pytest-hy";
      flake = false;
    };
    pytest-reverse = {
      url = "github:adamchainz/pytest-reverse/1.5.0";
      flake = false;
    };
    pytest-parametrized = {
      url = "github:coady/pytest-parametrized/v1.3";
      flake = false;
    };
    pytest-custom_exit_code = {
      url = "github:yashtodi94/pytest-custom_exit_code/0.3.0";
      flake = false;
    };
    pytest-ignore = {
      url = "github:syvlorg/pytest-ignore";
      flake = false;
    };
    dhall-python = {
      url =
        "github:s-zeng/dhall-python/cc14abd1f102959f8d27476514e64f1730b14ecc";
      flake = false;
    };
    sh = {
      url = "github:amoffat/sh";
      flake = false;
    };
    devenv.url = "github:cachix/devenv";
    orgparse = {
      url = "github:karlicoss/orgparse";
      flake = false;
    };
  };
  outputs = inputs@{ self, ... }:
    with builtins;
    let
      lib = inputs.nixpkgs.lib.extend (import ./lib.nix self inputs);
      lockfile = fromJSON (readFile ./flake.lock);
      Inputs = lib.iron.extendInputs inputs lockfile;
    in with lib;
    iron.mkOutputs.python {
      inherit self inputs;
      pname = "valiant";
      doCheck = true;
      mkOutputs = iron.mkOutputs.base self.overlays self.pname;
      overlayset = {
        official = {
          general = toList "git";
          python = toList "black";
        };
      };
      overlays = iron.fold.set [
        (iron.mapPassName {
          xonsh = pname: final: prev: {
            ${pname} = let
              inherit (final) python3Packages;
              override = { inherit python3Packages; };
            in (prev.${pname}.override override).overrideAttrs (old: {
              passthru = old.passthru // {
                withPackages = python-packages:
                  (final.${pname}.override override).overrideAttrs (old: {
                    propagatedBuildInputs = flatten [
                      (python-packages python3Packages)
                      (old.propagatedBuildInputs or [ ])
                    ];
                  });
              };
            });
          };
          qtile = pname: final: prev: {
            # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/pkgs/development/python-modules/qtile/wrapper.nix
            ${pname} = let inherit (final) python3Packages;
            in (final.python3.withPackages
              (_: [ python3Packages.${pname} ])).overrideAttrs (old: {
                # restore some qtile attrs, beautify name
                inherit (python3Packages.${pname}) pname version meta;
                name = with python3Packages.${pname}; "${pname}-${version}";
                passthru = old.passthru // {
                  unwrapped = python3Packages.${pname};
                  withPackages = python-packages:
                    final.${pname}.overrideAttrs (old: {
                      propagatedBuildInputs = flatten [
                        (python-packages python3Packages)
                        (old.propagatedBuildInputs or [ ])
                      ];
                    });
                };
              });
          };
        })
      ];
      callPackage = { callPackage, pythonOlder

        , addict, ansicolors, black, dhall-python, jsonnet, more-itertools
        , orjson, poetry2setup, python-rapidjson, pyyaml, rich-click, sh
        , xmltodict, xxhash

        # Non-Python Dependencies
        , nixfmt, nix, nickel, cue, git }:
        callPackage (iron.mkPythonPackage self [ ] {
          inherit (self) pname doCheck;
          owner = "syvlorg";
          src = ./.;
          disabled = pythonOlder "3.11";
          postPatch = ''
            substituteInPlace pyproject.toml --replace "poetry2setup = { git = \"https://github.com/syvlorg/poetry2setup.git\", branch = \"master\" }" ""
            substituteInPlace ${self.pname}/__init__.py --replace "str(resources / \"lib\" / \"lib\")" "\"${inputs.nixpkgs}/lib\""
          '';
          # pytestFlagsArray = [ "-vv" ];

          # Adapted From: https://github.com/NixOS/nix/issues/670#issuecomment-1211700127
          preCheck = "HOME=$(mktemp -d)";

          propagatedBuildInputs = [
            addict
            ansicolors
            black
            dhall-python
            jsonnet
            more-itertools
            orjson
            poetry2setup
            python-rapidjson
            pyyaml
            rich-click
            sh
            xxhash
            xmltodict

            # Non-Python Dependencies
            cue
            git
            nickel
            nix
            nixfmt
          ];
        }) { };
      callPackageset = {
        callPackages = iron.mapPassName {
          poetry2setup = pname:
            iron.toPythonApplication { appSrc = "${pname}.py"; } pname;
        };
        python = iron.mapPassName {
          click-aliases = pname:
            { buildPythonPackage, pythonOlder, click, makePythonPath }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              src = inputs.${pname};
              propagatedBuildInputs = [ click ];
              propagatedNativeBuildInputs = propagatedBuildInputs;
              postCheck = ''
                PYTHONPATH=${
                  makePythonPath [ propagatedNativeBuildInputs ]
                }:$PYTHONPATH
                python -c "import click_aliases"
              '';
              meta = {
                description = "enable aliases for click";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = licenses.mit;
              };
            };
          orgparse = pname:
            { buildPythonPackage, pythonOlder, setuptools-scm, fetchPypi
            , pytestCheckHook }:
            buildPythonPackage rec {
              inherit pname;
              version = "0.3.1";
              disabled = pythonOlder "3.7";
              src = fetchPypi {
                inherit pname version;
                sha256 = "sha256-hg5vu5pnt0K6p5LmD4zBhSLpeJwGXSaCHAIoXV/BBK8=";
              };
              propagatedBuildInputs = [ setuptools-scm ];
              propagatedNativeBuildInputs = propagatedBuildInputs;
              checkInputs = [ pytestCheckHook ];
              postPatch = ''
                substituteInPlace orgparse/__init__.py --replace "__all__ = [\"load\", \"loads\", \"loadi\"]" "__all__ = [\"load\", \"loads\", \"loadi\"]; __version__ = \"${version}\""
              '';
              meta = {
                description = "Python module for reading Emacs org-mode files";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = licenses.bsd2;
              };
            };
          pytest-hy = pname:
            { buildPythonPackage, pytest, hy, pythonOlder }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              disabled = pythonOlder "3.7";
              src = inputs.${pname};
              propagatedBuildInputs = [ pytest hy ];
              buildInputs = propagatedBuildInputs;
              doCheck = false;
              meta = {
                description = "The official hy conftest, as a pytest plugin!";
                license = licenses.mit;
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
              };
            };
          pytest-drop-dup-tests = pname:
            { buildPythonPackage, pythonOlder, pytestCheckHook, fetchPypi
            , setuptools-scm }:
            buildPythonPackage rec {
              inherit pname;
              version = "0.3.0";
              disabled = pythonOlder "3.7";
              src = fetchPypi {
                inherit pname version;
                hash = "sha256-bvmz3RkXETaxtelwo9gFk8y8UeNoSxty8QVKFmVrxWM=";
              };
              buildInputs = [ setuptools-scm ];
              checkInputs = [ pytestCheckHook ];
              meta = {
                description =
                  "A Pytest plugin to drop duplicated tests during collection";
                homepage =
                  "https://github.com/nicoddemus/pytest-drop-dup-tests";
                license = licenses.mit;
              };
            };
          pytest-ignore = pname:
            { buildPythonPackage, pythonOlder, pytest, git, sh }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              # version = "1.3";
              disabled = pythonOlder "3.7";
              src = inputs.${pname};
              nativeBuildInputs = [ pytest sh git ];
              checkPhase = ''
                cp tests/test_{0,ignored}.py
                pytest --ignore=tests/test_0.py tests
              '';
              meta = {
                description =
                  "A pytest plugin to ignore files from various .ignore files!";
                homepage = "https://github.com/syvlorg/pytest-ignore";
                license = licenses.mit;
              };
            };
          pytest-reverse = pname:
            { lib, buildPythonPackage, numpy, pytestCheckHook, pythonOlder }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              disabled = pythonOlder "3.7";
              src = inputs.${pname};
              checkInputs = [ pytestCheckHook ];
              pytestFlagsArray = [ "-p" "no:reverse" ];
              pythonImportsCheck = [ "pytest_reverse" ];
              meta = {
                description = "Pytest plugin to reverse test order.";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = licenses.mit;
              };
            };
          pytest-parametrized = pname:
            { buildPythonPackage, pythonOlder, pytestCheckHook, pytest-cov }:
            buildPythonPackage rec {
              inherit pname;
              version = iron.pyVersion "${src}/parametrized.py";
              disabled = pythonOlder "3.7";
              src = inputs.${pname};
              pythonImportsCheck = [ "parametrized" ];
              checkInputs = [ pytestCheckHook pytest-cov ];
              meta = {
                description =
                  "Pytest decorator for parametrizing tests with default iterables.";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = licenses.asl20;
              };
            };
          pytest-custom_exit_code = pname:
            { buildPythonPackage, pythonOlder, pytestCheckHook }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              disabled = pythonOlder "3.7";
              src = inputs.${pname};
              pythonImportsCheck = [ "pytest_custom_exit_code" ];
              checkInputs = [ pytestCheckHook ];
              meta = {
                description =
                  "Exit pytest test session with custom exit code in different scenarios";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = licenses.mit;
              };
            };
          poetry2setup = pname:
            { poetry-core, buildPythonPackage }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              format = "pyproject";
              src = inputs.${pname};
              propagatedBuildInputs = [ poetry-core ];
              propagatedNativeBuildInputs = propagatedBuildInputs;
              buildInputs = [ poetry-core ];
              nativeBuildInputs = buildInputs;
              meta = {
                description =
                  "Convert python-poetry(pyproject.toml) to setup.py.";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = licenses.mit;
              };
              passthru = { inherit format; };
            };

          # Adapted From: https://github.com/nixos/nixpkgs/blob/master/pkgs/development/python-modules/orjson/default.nix
          dhall-python = pname:
            { buildPythonPackage, pythonOlder, pytestCheckHook, pylint, flake8
            , pytest-benchmark, hypothesis, autopep8, maturin, perl
            , pytest-runner, rustPlatform, wheel
            , sha256 ? "sha256-2u9X2W0liw5fvwsb4QOcyV3LWSh02UU3UkIT1UgwlhQ=" }:
            buildPythonPackage rec {
              inherit pname;
              inherit (Inputs.${pname}) version;
              disabled = pythonOlder "3.7";
              src = inputs.${pname};
              cargoDeps = rustPlatform.fetchCargoTarball {
                inherit src sha256;
                name = "${pname}-${version}";
              };
              format = "pyproject";
              nativeBuildInputs = with rustPlatform; [
                perl
                cargoSetupHook
                maturinBuildHook
              ];
              checkInputs = [
                pylint
                flake8
                pytestCheckHook
                wheel
                pytest-runner
                pytest-benchmark
                hypothesis
                maturin
                autopep8
              ];
              doCheck = false;
              pythonImportsCheck = [ "dhall" ];
              meta = with lib; {
                description =
                  "Up-to-date and maintained python bindings for dhall, a functional configuration language";
                homepage =
                  "https://github.com/${Inputs.${pname}.owner}/${pname}";
                license = with licenses; [ asl20 mit ];
              };
            };
        };
      };
    } {
      base = true;
      isApp = true;
      channels.nixpkgs.config = iron.attrs.configs.nixpkgs;
      pythonOverlays = iron.mapPassName {
        rich = pname: final: prev:
          iron.update.python.package pname (pnpkgs: popkgs: old:
            let
              patches = (old.patches or [ ]) ++ [
                ./patches/rich/__init__.patch
                ./patches/rich/_inspect.patch
              ];
            in {
              patchPhase = concatStringsSep "\n"
                (map (patch: "patch -p 1 -uNi ${patch}") patches);
            }) final prev;
      };
    };
}
