{
    description = "Fine. I'll do it myself.";
    inputs = rec {
        flake-utils.url = github:numtide/flake-utils;
        flake-compat = {
            url = "github:edolstra/flake-compat";
            flake = false;
        };
        nixpkgs.url = github:nixos/nixpkgs/nixos-unstable;
    };
    outputs = inputs@{ self, nixpkgs, flake-utils, ... }: with builtins; with nixpkgs.lib; with flake-utils.lib; let
        pname = "thanos";
        type = "python3";
        workingSystems = subtractLists (flatten [
            (filter (system: hasPrefix "mips" system) allSystems)
            "x86_64-solaris"
        ]) allSystems;
        callPackage = { buildPythonPackage, pythonOlder, poetry-core, addict, click, makePythonPath }: buildPythonPackage rec {
            inherit pname;
            version = "1.0.0.0";
            src = ./.;
            format = "pyproject";
            disabled = pythonOlder "3.9";
            meta = {
                homepage = "https://github.com/syvlorg/${pname}";
                description = "Fine. I'll do it myself.";
            };
            propagatedBuildInputs = [ addict click ];
            propagatedNativeBuildInputs = propagatedBuildInputs;
            buildInputs = [ poetry-core ];
            nativeBuildInputs = buildInputs;
            postCheck = ''
                PYTHONPATH=${makePythonPath [ propagatedNativeBuildInputs ]}:$PYTHONPATH
                python -c "import ${concatStringsSep "; import " [ pname ]}"
            '';
            doCheck = false;
        };
        python = "python310";
        callApplication = { Python }: let
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
            installPhase = ''
                mkdir --parents $out/bin
                cp $src/${pname}/__init__.py $out/bin/${pname}
                chmod +x $out/bin/${pname}
            '';
            postFixup = "wrapProgram $out/bin/${pname} $makeWrapperArgs";
            makeWrapperArgs = [ "--prefix PYTHONPATH : ${ppkgs.makePythonPath propagatedBuildInputs}" ];
        }));
        overlayset = let
            overlay = final: prev: { ${pname} = final.callPackage callApplication {}; };
        in {
            overlays = rec {
                ${self.python} = final: prev: { ${self.python} = prev.${self.python}.override (super: {
                    packageOverrides = composeExtensions (super.packageOverrides or (_: _: {})) (new: old: {
                        ${pname} = new.callPackage callPackage {  };
                    });
                }); };
                Python = final: prev: { Python = final.${self.python}; };
                ${pname} = overlay;
                default = overlay;
            };
            inherit overlay;
            defaultOverlay = overlay;
        };
        mkApp = name: drv: { type = "app"; program = "${drv}${drv.passthru.exePath or "/bin/${drv.meta.mainprogram or drv.executable or drv.pname or drv.name or name}"}"; };
    in overlayset // (eachSystem workingSystems (system: rec {
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
        packages = flattenTree (rec {
            python = pkgs.${self.python}.withPackages (ppkgs: [ ppkgs.${pname} ]);
            python3 = python;
            ${self.python} = python;
            default = pkgs.${pname};
            ${pname} = default;
        });
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
    })) // { inherit callPackage python pname type; };
}