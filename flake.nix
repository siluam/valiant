{
    description = "Fine. I'll do it myself.";
    inputs = rec {
        flake-utils.url = github:numtide/flake-utils;
        flake-compat = {
            url = "github:edolstra/flake-compat";
            flake = false;
        };
        nixpkgs.url = github:nixos/nixpkgs/nixos-22.05;
        poetry2setup = {
            url = github:abersheeran/poetry2setup;
            flake = false;
        };
    };
    outputs = inputs@{ self, nixpkgs, flake-utils, ... }: with builtins; with nixpkgs.lib; with flake-utils.lib; let
        pname = "titan";
        type = "python3";
        callPoetry2Setup = { Python, gawk }: let
            inherit (Python.pkgs) buildPythonApplication poetry-core makePythonPath;
        in buildPythonApplication rec {
            pname = "poetry2setup";
            version = "1.0.0";
            format = "pyproject";
            src = inputs.${pname};
            propagatedBuildInputs = [ poetry-core ];
            propagatedNativeBuildInputs = propagatedBuildInputs;
            buildInputs = [ poetry-core ];
            nativeBuildInputs = buildInputs;
            installPhase = ''
                mkdir --parents $out/bin
                cp $src/${pname}.py $out/bin/${pname}
                chmod +x $out/bin/${pname}
                
                # Adapted from [[https://unix.stackexchange.com/users/28765/rudimeier][rudimeier's]] answer [[https://unix.stackexchange.com/a/313025/270053][here]]:
                ${gawk}/bin/awk -i inplace 'BEGINFILE{print "#!/usr/bin/env python3"}{print}' $out/bin/${pname}
            '';
            postFixup = "wrapProgram $out/bin/${pname} $makeWrapperArgs";
            makeWrapperArgs = [ "--prefix PYTHONPATH : ${makePythonPath propagatedNativeBuildInputs}" ];
            meta = {
                description = "Convert python-poetry(pyproject.toml) to setup.py.";
                homepage = "https://github.com/abersheeran/${pname}";
                license = licenses.mit;
            };
        };
        callPackage = { buildPythonPackage, pythonOlder, poetry-core, addict, click, rich, makePythonPath }: buildPythonPackage rec {
            inherit pname;
            version = "1.0.0.0";
            src = ./.;
            format = "pyproject";
            disabled = pythonOlder "3.9";
            meta = {
                homepage = "https://github.com/syvlorg/${pname}";
                description = "Fine. I'll do it myself.";
            };
            propagatedBuildInputs = [ addict click rich ];
            propagatedNativeBuildInputs = propagatedBuildInputs;
            buildInputs = [ poetry-core ];
            nativeBuildInputs = buildInputs;
            postCheck = ''
                PYTHONPATH=${makePythonPath [ propagatedNativeBuildInputs ]}:$PYTHONPATH
                python -c "import ${concatStringsSep "; import " [ pname ]}"
            '';
            doCheck = false;
            passthru = { inherit format disabled; };
        };
        python = "python310";
        callApplication = { Python, poetry2setup }: let
            ppkgs = Python.pkgs;
        in ppkgs.buildPythonApplication ((filterAttrs (n: v: ! ((isDerivation v) || (elem n [
            "drvAttrs"
            "override"
            "overrideAttrs"
            "overrideDerivation"
            "overridePythonAttrs"
        ]))) ppkgs.${pname}) // (rec {
            propagatedBuildInputs = toList ppkgs.${pname};
            propagatedNativeBuildInputs = propagatedBuildInputs;
            buildInputs = toList poetry2setup;
            nativeBuildInputs = buildInputs;
            installPhase = ''
                mkdir --parents $out/bin
                cp $src/${pname}/__init__.py $out/bin/${pname}
                chmod +x $out/bin/${pname}
            '';
            postFixup = "wrapProgram $out/bin/${pname} $makeWrapperArgs";
            makeWrapperArgs = [
                "--prefix PYTHONPATH : ${ppkgs.makePythonPath propagatedBuildInputs}"
                "--prefix PATH : ${makeBinPath nativeBuildInputs}"
            ];
        }));
        overlayset = let
            overlay = final: prev: { ${pname} = final.callPackage callApplication {}; };
        in {
            overlays = rec {
                "python3-${pname}" = python;
                ${pname} = overlay;
                ${self.python} = python;
                default = overlay;
                poetry2setup = final: prev: { poetry2setup = final.callPackage callPoetry2Setup {}; };
                Python = final: prev: { Python = final.${self.python}; };
                python = final: prev: { ${self.python} = prev.${self.python}.override (super: {
                    packageOverrides = composeExtensions (super.packageOverrides or (_: _: {})) (new: old: { ${pname} = new.callPackage callPackage {  }; });
                }); };
                python3 = python;
            };
            inherit overlay;
            defaultOverlay = overlay;
        };
        mkApp = name: drv: { type = "app"; program = "${drv}${drv.passthru.exePath or "/bin/${drv.meta.mainprogram or drv.executable or drv.pname or drv.name or name}"}"; };
        outputs = eachDefaultSystem (system: rec {
            pkgs = import nixpkgs {
                overlays = attrValues overlayset.overlays;
                inherit system;
                allowUnfree = true;
                allowBroken = true;
                allowUnsupportedSystem = true;
                # preBuild = ''
                #     makeFlagsArray+=(CFLAGS="-w")
                #     buildFlagsArray+=(CC=cc)
                # '';
                permittedInsecurePackages = [
                    "python2.7-cryptography-2.9.2"
                ];
            };
            legacyPackages = pkgs;
            packages = flattenTree rec {
                "python3-${pname}" = python;
                ${pname} = default;
                ${self.python} = python;
                default = pkgs.${pname};
                poetry2setup = pkgs.poetry2setup;
                Python = pkgs.Python;
                python = pkgs.${self.python}.withPackages (ppkgs: [ ppkgs.${pname} ]);
                python3 = python;
            };
            package = packages.default;
            defaultPackage = package;
            apps = mapAttrs mkApp packages;
            app = apps.default;
            defaultApp = app;
            devShells = let
                makefile = pkgs.mkShell rec {
                    buildInputs = unique (attrValues packages);
                    nativeBuildInputs = buildInputs;
                };
            in (mapAttrs (n: v: pkgs.mkShell rec {
                buildInputs = [ v ];
                nativeBuildInputs = buildInputs;
            }) packages) // (rec {
                inherit makefile;
                makefile-general = makefile;
                "makefile-${type}" = makefile;
            });
            devShell = devShells.default;
            defaultDevShell = devShell;
        });
    in overlayset // outputs // {
        inherit callPackage python pname type;
        testType = "python";
    } // (listToAttrs (map (system: nameValuePair system (mapAttrs (n: v: v.${system}) outputs)) defaultSystems));
}