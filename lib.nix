flake: linputs: lfinal: lprev:
with builtins;
with lfinal; {
  isAttrsOnly = v: (isAttrs v) && (!(isDerivation v));

  # TODO: Remove the tryEval from here
  # recursiveUpdateAll = delim: a: b:
  #   let a-names = attrNames a;
  #   in (mapAttrs (n: v:
  #     let e = tryEval v;
  #     in if (e.success && (isAttrsOnly v)) then
  #       (if (any (attr:
  #         let g = tryEval attr;
  #         in g.success
  #         && ((isAttrsOnly attr) || (isList attr) || (isString attr)))
  #         (attrValues v)) then
  #         (recursiveUpdateAll delim v (b.${n} or { }))
  #       else
  #         (v // (b.${n} or { })))
  #     else if (isList v) then
  #       (v ++ (b.${n} or [ ]))
  #     else if ((delim != null) && (isString v)) then
  #       (if (hasAttr n b) then (v + delim + b.${n}) else v)
  #     else
  #       (b.${n} or v)) a) // (removeAttrs b a-names);
  recursiveUpdateAll = delim: a: b:
    let a-names = attrNames a;
    in (mapAttrs (n: v:

      # TODO: Is this `tryEval' necessary?
      let e = tryEval v;
      in if (e.success && (any id [ (isAttrsOnly v) ])) then

      # TODO: Need this to merge mkShells
      # in if (e.success && ((isAttrsOnly v) || (v ? shellHook))) then

      # (if (any (attr: (isAttrs attr) || (isList attr) || (isString attr))
      #   (attrValues v)) then
      #   (recursiveUpdateAll delim v (b.${n} or { }))
      # else
      #   (v // (b.${n} or { })))
        (recursiveUpdateAll delim v (b.${n} or { }))
      else if (e.success && (isDerivation v)
        && (b.${n}.__append__ or false)) then
        (recursiveUpdateAll delim v (removeAttrs b.${n} [ "__append__" ]))
      else if (isList v) then
        (v ++ (b.${n} or [ ]))
      else if ((delim != null) && (isString v)) then
        (if (hasAttr n b) then (v + delim + b.${n}) else v)
      else
        (b.${n} or (if (n == "overridePythonAttrs") then "" else v))) a)
    // (removeAttrs b a-names);

  # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/lib/fixed-points.nix#L71
  mergeExtensions = f: g: final: prev:
    let
      fApplied = f final prev;
      prev' = recursiveUpdateAll null prev fApplied;
    in recursiveUpdateAll null fApplied (g final prev');

  # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/lib/fixed-points.nix#L80
  mergeManyExtensions = foldr (x: y: mergeExtensions x y) (final: prev: { });

  # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/lib/fixed-points.nix#L40
  mergeExtends = f: rattrs: self:
    let super = rattrs self;
    in (recursiveUpdateAll null super (f self super));

  # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/lib/fixed-points.nix#L107
  mkMergeExtensibleWithCustomName = extenderName: rattrs:
    fix' (self:
      (rattrs self) // {
        ${extenderName} = f:
          mkMergeExtensibleWithCustomName extenderName (mergeExtends f rattrs);
      });

  # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/lib/fixed-points.nix#L89
  mkMergeExtensible = mkMergeExtensibleWithCustomName "extend";

  iron = mkMergeExtensible (lself: {
    listToString = map (v: ''"${v}"'');
    valiant = flake;
    extendIron = lib: func:
      lib.extend (final: prev: { iron = prev.iron.extend (func final prev); });
    deepEval = e: tryEval (deepSeq e e);

    passName = n: v: v n;
    mapPassName = mapAttrs iron.passName;

    mapAttrNames = f: mapAttrs' (n: v: nameValuePair (f n v) v);
    libbed = hasSuffix "-lib";
    liberate = n: if (iron.libbed n) then n else (n + "-lib");
    libify = iron.mapAttrNames (n: v: iron.liberate n);
    genLibs = f: mapAttrs' (n: v: nameValuePair (iron.liberate n) (f n v));

    # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/lib/attrsets.nix#L406
    genAttrNames = values: f:
      listToAttrs (map (v: nameValuePair (f v) v) values);

    attrs = {
      versions.python = "python311";
      channel = rec {
        value = "23.05";
        dashed = replaceStrings [ "." ] [ "-" ] iron.attrs.channel.value;
        comparison =
          compareVersions linputs.nixpkgs.lib.version iron.attrs.channel.value;
        older = comparison == (0 - 1);
        default = comparison == 0;
        newer = comparison == 1;
      };
      packages.python = [
        "python"
        "python3"
        iron.attrs.versions.python
        "xonsh"
        "qtile"
        "hy"
        # "pypy3"
      ];
      inputPrefixes.python = "py";
      configs = {
        nixpkgs = {
          allowUnfree = true;
          allowBroken = true;
          allowUnsupportedSystem = true;
          # preBuild = ''
          #     makeFlagsArray+=(CFLAGS="-w")
          #     buildFlagsArray+=(CC=cc)
          # '';
          # permittedInsecurePackages = [
          #     "python2.7-cryptography-2.9.2"
          # ];
        };
      };
      checkInputs = {
        python = [
          "pytest-custom_exit_code"
          "pytest-drop-dup-tests"
          "pytest-lazy-fixture"
          "pytest-order"
          "pytest-parametrized"
          "pytest-randomly"
          "pytest-repeat"
          "pytest-sugar"
          # "pytest-ordering"
        ];
      };
      buildInputs = {
        general = [ "yq" "valiant" "git" "busybox" ];
        python = {
          apps = [ "poetry2setup" ];
          pkgs = flatten [ "pytest" iron.attrs.checkInputs.python ];
        };
      };
      packageSets = iron.fold.set [
        (mapAttrs (n: v: [ v "pkgs" ]) iron.attrs.versions)
        { general = [ ]; }
      ];
      overriders = {
        default = "overrideAttrs";
        python = "overridePythonAttrs";
      };
    };

    mkInputs = inputs': pure:
      mapAttrs (n: v: v (inputs'.${n}.pkgs or inputs'.${n} or [ ])) {
        python = inputs:
          { type ? "general", parallel ? true, ... }:
          flatten [
            inputs
            (optional (type == "hy") "pytest-hy")
            (optional parallel "pytest-xdist")
            (optional (!pure) "pytest-ignore")
          ];
      };

    mkBuildInputs = iron.mkInputs iron.attrs.buildInputs false;
    mkCheckInputs = iron.mkInputs iron.attrs.checkInputs true;

    getGroup = type:
      let
        packageTypes = remove null
          (mapAttrsToList (n: v: iron.mif.null (elem type v) n)
            iron.attrs.packages);
      in if (packageTypes != [ ]) then
        (head packageTypes)
      else if (hasPrefix "emacs" type) then
        "emacs"
      else
        "general";

    getAttrFromPath = set: group: attrByPath [ group ] set.default set;
    getOverrider = iron.getAttrFromPath iron.attrs.overriders;

    filterAttrs = f: list: filterAttrs (n: v: (elem n list) && (f v));
    filterAttrs' = f: list: filterAttrs (n: v: (elem n list) && (f n v));
    getFromAttrs = attr: map (getAttr attr);
    getFromAttrsDefault = list: attr: default:
      map (attrByPath [ attr ] default) list;

    makefile = let
      inherit (iron)
        getFromAttrsDefault fold filters mkWithPackages getOverrider dontCheck
        mapPassName mkBuildInputs;
      merger = args@{ group ? "general", type ? "general", ... }:
        getFromAttrsDefault [
          (args.groups.${group} or { })
          (args.types.${type} or { })
        ];
      base = args@{ pname, pkgs, group ? "general", type ? "general", ... }:
        let
          removals = flatten [ "propagatedBuildInputs" (attrNames dependents) ];
          bases = fold.stringMerge [
            {
              buildInputs = filters.has.list [
                iron.attrs.buildInputs.general
                (iron.attrs.buildInputs.${group}.apps or [ ])
                (if (isDerivation pname) then
                  [ (pname.buildInputs or [ ]) ]
                else [
                  (pkgs.${pname}.buildInputs or [ ])
                  ((getAttrFromPath iron.attrs.packageSets.${group}
                    pkgs).${pname}.buildInputs or [ ])
                ])
              ] pkgs;
            }
            (removeAttrs (args.groups.${group} or { }) removals)
            (removeAttrs (args.types.${type} or { }) removals)
          ];
          dependents = fold.stringMerge [
            (mapPassName {
              nativeBuildInputs = attr:
                filters.has.list [
                  bases.buildInputs
                  (if (isDerivation pname) then
                    [ (pname.${attr} or [ ]) ]
                  else [
                    (pkgs.${pname}.${attr} or [ ])
                    ((getAttrFromPath iron.attrs.packageSets.${group}
                      pkgs).${pname}.${attr} or [ ])
                  ])
                  (merger args attr [ ])
                ] pkgs;
            })
          ];
        in pkgs.mkShell (fold.set [ bases dependents ]);
      default = args@{ pname, pkgs, parallel ? true, group ? "general"
        , type ? "general", ... }:
        base ((fold.merge [
          {
            groups.${group}.buildInputs = toList (mkWithPackages pkgs.${type} [
              ((mkBuildInputs.${group} or (_: { ... }: _)) {
                inherit type parallel;
              })
              (merger args "propagatedBuildInputs" [ ])
            ] pname);
          }
          (removeAttrs args [ "pkgs" ])
        ]) // {
          inherit pkgs;
        });
      mkfiles = genAttrs (attrNames iron.attrs.versions) (group:
        args@{ pname, pkgs, ... }:
        iron.makefile.default (fold.set [
          args
          {
            inherit group;
            pname =
              (getAttrFromPath iron.attrs.packageSets.${group} pkgs).${pname}.${
                getOverrider group
              } dontCheck;
          }
        ]));
    in fold.set [
      mkfiles
      {
        inherit base default;
        general = args@{ ... }: base (removeAttrs args [ "group" "type" ]);
        echo = fold.set [
          {
            default = var: pkgs: envs:
              fold.shell pkgs [ envs { shellHook = "echo \$${var}; exit"; } ];
            general = var:
              args@{ pkgs, ... }:
              iron.makefile.echo.default var pkgs (iron.makefile.general args);
          }
          (mapAttrs (n: v: var:
            args@{ pkgs, ... }:
            iron.makefile.echo.default var pkgs (v args)) mkfiles)
        ];
        path = mapAttrs (n: v: v "PATH") iron.makefile.echo;
      }
    ];

    makefiles = args@{ pname, pkgs, parallel ? true, group ? "general"
      , type ? "general", ... }:
      let
        inherit (iron) attrs fold makefile mapAttrNames;
        not-general = !((group == "general") && (type == "general"));
        packages = if group == "emacs" then
          (attrNames pkgs.emacsen)
        else
          attrs.packages.${group};
        mkfiles = let
          typefiles = genAttrs packages
            (type: makefile.${group} (fold.set [ args { inherit type; } ]));
        in fold.set [
          { general = makefile.general args; }
          (optionals not-general [
            typefiles
            { ${group} = typefiles.${attrs.versions.${group}}; }
          ])
        ];
        mkpaths = mapAttrs (n: makefile.path.default pkgs) mkfiles;
      in fold.set [
        {
          makefile = mkfiles.${type};
          makefile-path = mkpaths.${type};
        }
        (mapAttrNames (n: v: "makefile-${n}") mkfiles)
        (mapAttrNames (n: v: "makefile-${n}-path") mkpaths)
        (optionalAttrs (group == "python") (let
          pythonpaths = mapAttrs' (n: v:
            nameValuePair "makefile-${n}-pythonpath"
            (makefile.echo.default "PYTHONPATH" pkgs v))
            (filterAttrs (n: v: elem n packages) mkfiles);
        in fold.set [
          pythonpaths
          { makefile-pythonpath = pythonpaths."makefile-${type}-pythonpath"; }
        ]))
      ];

    inputTypeTo = func: suffix:
      mapAttrs (n: v: func (v + suffix)) iron.attrs.inputPrefixes;
    inputPkgsTo = flip iron.inputTypeTo "Pkg";
    inputAppsTo = flip iron.inputTypeTo "App";
    inputBothTo = func:
      genAttrs (attrNames iron.attrs.inputPrefixes) (pkg: inputs:
        ((iron.inputPkgsTo func).${pkg} inputs)
        // ((iron.inputAppsTo func).${pkg} inputs));

    inputToOverlays = prefix: inputs:
      iron.fold.set (mapAttrsToList
        (N: V: filterAttrs (n: v: iron.libbed n) (V.overlays or { }))
        (filterAttrs (n: v: hasPrefix "${prefix}-" n) inputs));
    inputTypeToOverlays = with iron; inputTypeTo inputToOverlays;
    inputPkgsToOverlays = iron.inputTypeToOverlays "Pkg";
    inputAppsToOverlays = iron.inputTypeToOverlays "App";
    inputBothToOverlays = with iron; inputBothTo inputToOverlays;

    inputToPackages = prefix': inputs:
      let prefix = prefix' + "-";
      in map (removePrefix prefix)
      (attrNames (filterAttrs (n: v: hasPrefix prefix n) inputs));
    inputTypeToPackages = with iron; inputTypeTo inputToPackages;
    inputPkgsToPackages = iron.inputTypeToPackages "Pkg";
    inputAppsToPackages = iron.inputTypeToPackages "App";
    inputBothToPackages = with iron; inputBothTo inputToPackages;

    # `filters.has.list' is an incomplete function; the general form of `withPackages~ is ~(pkgs: ...)',
    # where the full form of `filters.has.list' would be `(pkgs: filters.has.list [...] pkgs)'.

    # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/doc/builders/packages/emacs.section.md#configuring-emacs-sec-emacs-config
    mkWithPackages = pkg: pkglist: pname:
      pkg.withPackages (iron.filters.has.list [
        pkglist
        pname
        (optional (pkg.pname == "hy") "hyrule")
      ]);

    mkApp = name: drv:
      let
        DRV =
          iron.filterAttrs (attr: !(isBool attr)) [ "exe" "executable" ] drv;
      in {
        type = "app";
        program = "${drv}${
            drv.passthru.exePath or "/bin/${
              drv.meta.mainprogram or drv.meta.mainProgram or DRV.exe or DRV.executable or drv.pname or drv.name or name
            }"
          }";
      };

    # This generates the packages for only the current project
    groupOutputs = pname: packages: isApp: type:
      let
        inherit (iron) mkWithPackages fold mapAttrNames;
        versions = mapAttrs (n: v: mkWithPackages v [ ] pname) packages;
      in fold.set [
        versions
        (mapAttrNames (n: v: "${n}-${pname}") versions)
        (optionalAttrs (!isApp)
          (genAttrs [ "default" pname ] (package: versions.${type})))
      ];

    # This generates the packages for all the overlays
    withPackages = overlays: packages:
      let inherit (iron) fold mkWithPackages;
      in fold.set [
        (mapAttrs (n: v: mkWithPackages v (attrNames overlays)) packages)
        (listToAttrs (flatten (mapAttrsToList (n: v:
          map (pkg':
            let pkg = removeSuffix "-lib" pkg';
            in nameValuePair "${n}-${pkg}" (mkWithPackages v [ ] pkg))
          (attrNames overlays)) packages)))
      ];

    mkPackages = overlays: packages: pname: isApp: type: currentLanguage:
      let inherit (iron) fold withPackages groupOutputs;
      in fold.set [
        (withPackages overlays packages)
        (optionalAttrs currentLanguage (groupOutputs pname packages isApp type))
      ];

    getCallPackages = plus: args:
      iron.fold.set [
        (plus.callPackages or { })
        (plus.callPackageset.callPackages or { })
      ];

    getCallPackage = plus: args:
      let
        _ = plus.callPackage or (iron.getCallPackages plus
          args).default or (throw ''
            Sorry! One of the following must be provided:
            - callPackage
            - callPackages.default
            - callPackageset.callPackages.default
            - overlay
            - preOverlays.default
            - overlayset.preOverlays.default
            - overlays.default
            - overlayset.overlays.default
          '');
      in {
        callPackage = _.package or _;
        inheritance = _.inheritance or { };
      };

    filterInheritance = pkg: inheritance:
      let args = functionArgs (if (isFunction pkg) then pkg else (import pkg));
      in filterAttrs (n: v: hasAttr n args) inheritance;

    callPackageFilter = callPackage: pkg: inheritance:
      callPackage pkg (iron.filterInheritance pkg inheritance);

    getOverlays = plus: args:
      iron.fold.set [
        (args.preOverlays or { })
        (plus.overlayset.preOverlays or { })
        (plus.overlays or { })
        (plus.overlayset.overlays or { })
      ];

    getOverlay = plus: args:
      plus.overlay or (iron.getOverlays plus args).default or null;

    # Adapted From: https://github.com/nixos/nixpkgs/blob/master/lib/debug.nix
    traceValSeqFn = f: v: traceSeq (f v) v;
    traceValSeq = iron.traceValSeqFn id;
    traceFn = f: v: trace (f v) v;

    foldOrFlake = mkFlake: list:
      let inherit (iron) fold;
      in if mkFlake then
        (linputs.flake-utils-plus.lib.mkFlake (fold.merge list))
      else
        (fold.merge list);

    any = any id;
    all = all id;

    getOfficialOverlays = group: inputs: overlayset:
      iron.fold.set [
        (map (input: input.overlayset.official.${group} or { })
          (attrValues inputs))
        (overlayset.official.${group} or { })
      ];

    inheritAttr = name: attrs: { ${name} = attrs.${name}; };

    # "Tooled Overlays" are overlays that come with specific tools,
    # like "valiant" or "bundle".
    mkOutputs = let
      base = baseOverlays: tooledOverlays: tool: olib: languages:
        let
          inherit (olib) iron;
          inherit (iron)
            foldOrFlake callPackageFilter filterInheritance filters has fold
            getCallPackage getCallPackages getGroup getOverlay getOverlays
            libify makefiles mif mifNotNull mkApp mkPackages toPythonApplication
            update genLibs swapSystemOutputs;
          inherit (linputs.flake-utils.lib) eachSystem filterPackages;
          inherit (linputs.flake-utils-plus.lib) defaultSystems;
          bothOverlays = baseOverlays.__extend__
            (if (isFunction tooledOverlays) then
              tooledOverlays
            else
              (_: _: tooledOverlays));
          mkOutputs = base bothOverlays { } tool olib { };

          # Have to use the modified `mkOutputs'
          mkLanguage = outputs: mkOutputs.general outputs.plus outputs.args;

          mkLanguages = mapAttrs
            (n: v: plus: args: v ((args.language or "general") == n) plus args)
            (fold.set [
              {

                # IMPORTANT: Only keep the arguments that have default
                #            values specific to this function,
                #            are required arguments,
                #            or are used more than once.
                python = currentLanguage:
                  plus@{ self, inputs, pname

                  # These have to be explicitly inherited in the output,
                  # as they may not be provided by the end user
                  , type ? iron.attrs.versions.python, doCheck ? true
                  , callPackageset ? { }

                  , ... }:
                  args@{ isApp ? false, pythonOverlays ? { }, ... }:
                  let
                    gottenCallPackage = getCallPackage plus args;
                    inherit (gottenCallPackage) callPackage;
                    inheritance = filterInheritance callPackage
                      (gottenCallPackage.inheritance
                        // (args.inheritance or { }));
                    default = mifNotNull.default (getOverlay plus args)
                      (final: prev:
                        update.python.callPython inheritance pname callPackage
                        final prev);
                    systemOutputs = pkgs: {
                      packages =
                        filterPackages pkgs.stdenv.targetPlatform.system
                        (mkPackages self.overlayset.python pkgs.pythons pname
                          isApp type currentLanguage);
                    };
                  in {
                    plus = fold.merge [
                      (if (args.mkFlake or false) then {
                        outputsBuilder = channels:
                          systemOutputs channels.${plus.channel or "nixpkgs"};
                      } else
                        (eachSystem (args.supportedSystems or defaultSystems)
                          (system: systemOutputs self.pkgs.${system})))
                      (optionalAttrs currentLanguage {
                        inherit type doCheck callPackageset;
                      })
                      {
                        ${mif.null currentLanguage "overlay"} = if isApp then
                          (final: prev: {
                            # IMPORTANT: Because `attrValues' sorts attribute set items
                            #            alphabetically, if you add a `default' package,
                            #            packages whose names start with letters later on
                            #            in the alphabet will always override earlier
                            #            packages, such as `valiant' overriding `tailapi'.
                            ${pname} = final.callPackage
                              (toPythonApplication (args.extras or { }) pname)
                              inheritance;
                          })
                        else
                          default;
                        overlayset.python = fold.set [
                          (optionalAttrs currentLanguage {
                            "${pname}-lib" = default;
                          })
                          (genLibs (n: v: final: prev:
                            let cpkg = v.package or v;
                            in update.python.callPython (fold.set [
                              { pname = n; }
                              (args.inheritance or { })
                              (v.inheritance or { })
                            ]) n cpkg final prev)
                            (callPackageset.python or { }))
                          pythonOverlays
                        ];
                      }
                      plus
                    ];
                    inherit args;
                  };
              }
              languages
            ]);
        in fold.set [
          {
            base = base bothOverlays;
            general = plus@{ self, inputs, pname

              # TODO: Maybe use `functionArgs' instead, excluding specific arguments?
              # These have to be explicitly inherited in the output,
              # as they may not be provided by the end user
              , doCheck ? false, group ? (getGroup type), type ? "general"
              , parallel ? true, channel ? "nixpkgs", overlayset ? { }
              , callPackageset ? { }

              , overlays ? { }, supportedSystems ? defaultSystems
              , outputsBuilder ? (_: { }), ... }:
              args@{ preOutputs ? { }, preOverlays ? { }

                # If provided, `args.lib or lfinal' will be extended with this function
              , extensor ? null

                # If provided, `args.lib or lfinal' will be extended with this set
              , extension ? null

              , isApp ? false, mkFlake ? false, channelNames ? { }
              , patchGlobally ? false, languages ? false, base ? false, ... }:
              let
                composeLanguages = list:
                  recursiveUpdate
                  (foldl (a: b: b a.plus a.args) { inherit plus args; } list) {
                    args.languages = false;
                  };
                channelConfigs = fold.merge [
                  {
                    ${channel} = {
                      ${
                        mif.null (!((args.channels.${channel} or { }) ? input))
                        "input"
                      } = inputs.${channel} or linputs.${channel};
                      overlays = attrValues (self.overlays);
                    };
                  }
                  (args.channels or { })
                ];
                lib = let base = args.lib or lfinal;
                in if (extensor != null) then
                  (base.extend extensor)
                else if (extension != null) then
                  (base.extend (_: _: extension))
                else
                  base;
                gottenCallPackage = getCallPackage plus args;
                inherit (gottenCallPackage) callPackage inheritance;
                default = mifNotNull.default (getOverlay plus args)
                  (final: prev: {
                    # IMPORTANT: Because `attrValues' sorts attribute set items
                    #            alphabetically, if you add a `default' package,
                    #            packages whose names start with letters later on
                    #            in the alphabet will always override earlier
                    #            packages, such as `valiant' overriding `tailapi'.
                    ${pname} = callPackageFilter final.callPackage callPackage
                      (fold.set [
                        { inherit pname; }
                        (args.inheritance or { })
                        gottenCallPackage.inheritance
                      ]);
                  });
                fupRemove = outputs:
                  fold.set [
                    (if mkFlake then
                      (removeAttrs (recursiveUpdate outputs
                        (removeAttrs (outputs.channels.${channel} or { })
                          [ "overlaysBuilder" ])) [ "outputsBuilder" ])
                    else
                      (removeAttrs outputs [ "supportedSystems" ]))
                    (optionalAttrs (outputs ? devShells) {
                      devShells = mapAttrs (N: V:
                        if (elem N supportedSystems) then
                          (filterAttrs (n: v: !(hasSuffix "-devenv" n)) V)
                        else
                          V) outputs.devShells;
                    })
                  ];
                channelTool = plus.channel or tool;
                systemOutputs = system: channels: pkgs: {
                  inherit channels pkgs;
                  ${mif.null (!mkFlake) "legacyPackages"} = pkgs;
                  packages = filterPackages system (filters.has.attrs [
                    (subtractLists (attrNames
                      (inputs.${channelTool}.pkgs or inputs.${channelTool}.legacyPackages or inputs.${channelTool}.packages or inputs.valiant.pkgs).${system})
                      (attrNames pkgs))
                    (attrNames self.overlays)
                    {
                      default =
                        plus.packages.${system}.default or pkgs.${pname};
                    }
                  ] pkgs);
                  defaultPackage = self.packages.${system}.default;
                  package = self.defaultPackage.${system};
                  apps = let
                    prefix = ''
                      if [ -d "$1" ]; then
                        dir="$1"
                        shift 1
                      else
                        dir="$(${pkgs.git}/bin/git rev-parse --show-toplevel)" || "./."
                      fi
                      confnix=$(mktemp)
                      cp "${
                        inputs.bundle or inputs.valiant or "$dir"
                      }/default.nix" $confnix
                      substituteStream() {
                          local var=$1
                          local description=$2
                          shift 2

                          while (( "$#" )); do
                              case "$1" in
                                  --replace)
                                      pattern="$2"
                                      replacement="$3"
                                      shift 3
                                      local savedvar
                                      savedvar="''${!var}"
                                      eval "$var"'=''${'"$var"'//"$pattern"/"$replacement"}'
                                      if [ "$pattern" != "$replacement" ]; then
                                          if [ "''${!var}" == "$savedvar" ]; then
                                              echo "substituteStream(): WARNING: pattern '$pattern' doesn't match anything in $description" >&2
                                          fi
                                      fi
                                      ;;

                                  --subst-var)
                                      local varName="$2"
                                      shift 2
                                      # check if the used nix attribute name is a valid bash name
                                      if ! [[ "$varName" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
                                          echo "substituteStream(): ERROR: substitution variables must be valid Bash names, \"$varName\" isn't." >&2
                                          return 1
                                      fi
                                      if [ -z ''${!varName+x} ]; then
                                          echo "substituteStream(): ERROR: variable \$$varName is unset" >&2
                                          return 1
                                      fi
                                      pattern="@$varName@"
                                      replacement="''${!varName}"
                                      eval "$var"'=''${'"$var"'//"$pattern"/"$replacement"}'
                                      ;;

                                  --subst-var-by)
                                      pattern="@$2@"
                                      replacement="$3"
                                      eval "$var"'=''${'"$var"'//"$pattern"/"$replacement"}'
                                      shift 3
                                      ;;

                                  *)
                                      echo "substituteStream(): ERROR: Invalid command line argument: $1" >&2
                                      return 1
                                      ;;
                              esac
                          done

                          printf "%s" "''${!var}"
                      }

                      # put the content of a file in a variable
                      # fail loudly if provided with a binary (containing null bytes)
                      consumeEntire() {
                          # read returns non-0 on EOF, so we want read to fail
                          if IFS=''' read -r -d ''' $1 ; then
                              echo "consumeEntire(): ERROR: Input null bytes, won't process" >&2
                              return 1
                          fi
                      }

                      substitute() {
                          local input="$1"
                          local output="$2"
                          shift 2

                          if [ ! -f "$input" ]; then
                              echo "substitute(): ERROR: file '$input' does not exist" >&2
                              return 1
                          fi

                          local content
                          consumeEntire content < "$input"

                          if [ -e "$output" ]; then chmod +w "$output"; fi
                          substituteStream content "file '$input'" "$@" > "$output"
                      }

                      substituteInPlace() {
                          local -a fileNames=()
                          for arg in "$@"; do
                              if [[ "$arg" = "--"* ]]; then
                                  break
                              fi
                              fileNames+=("$arg")
                              shift
                          done

                          for file in "''${fileNames[@]}"; do
                              substitute "$file" "$file" "$@"
                          done
                      }
                    '';
                    shell = devShell: pure:
                      pkgs.writeShellScriptBin "shell" ''
                        ${prefix}
                        substituteInPlace $confnix \
                          --replace "(getFlake (toString ./.))" "(getFlake (toString ./.)).devShells.${system}.${devShell}" \
                          --replace ".defaultNix" ".defaultNix.devShells.${system}.${devShell}" \
                          --replace "./." "$dir" \
                          --replace "./flake.lock" "$dir/flake.lock"
                        trap "rm $confnix" EXIT
                        nix-shell --show-trace ${
                          if pure then "--pure" else "--impure"
                        } $confnix "$@"
                      '';

                    # Adapted From: https://github.com/NixOS/nix/issues/3803#issuecomment-748612294
                    #               https://github.com/nixos/nixpkgs/blob/master/pkgs/stdenv/generic/setup.sh#L818
                    repl = pkgs.writeShellScriptBin "repl" ''
                      ${prefix}
                      substituteInPlace $confnix \
                        --replace "./." "$dir" \
                        --replace "./flake.lock" "$dir/flake.lock"
                      trap "rm $confnix" EXIT
                      nix --show-trace -L repl $confnix
                    '';

                    repls =
                      genAttrs [ "repl" "${pname}-repl" ] (flip mkApp repl);
                  in fold.set [
                    (mapAttrs mkApp self.packages.${system})
                    repls
                    (map (pure:
                      mapAttrs' (n: v:
                        let
                          name =
                            "nix-shell-${if pure then "pure-" else ""}${n}";
                        in nameValuePair name (mkApp name (shell n pure)))
                      self.devShells.${system}) [ true false ])
                  ];
                  defaultApp = self.apps.${system}.default;
                  app = self.defaultApp.${system};
                  devShell = pkgs.mkShell {
                    buildInputs = [ pkgs.busybox self.package.${system} ];
                  };
                  defaultDevShell = self.devShell.${system};
                  devShells = with pkgs;
                    let
                      devShells = fold.set [
                        (mapAttrs
                          (n: v: mkShell { buildInputs = [ pkgs.busybox v ]; })
                          (fold.set [
                            self.packages.${system}
                            { "iron-envrc" = [ git bundle ]; }
                          ]))
                        (makefiles { inherit pname parallel type group pkgs; })
                        {
                          default = self.devShell.${system};
                          ${pname} = self.devShell.${system};
                        }
                      ];
                    in fold.set [
                      devShells
                      (mapAttrs' (n: v:
                        let name = "${n}-devenv";
                        in nameValuePair name (linputs.devenv.lib.mkShell {
                          inherit inputs pkgs;
                          modules = [
                            {
                              packages = with v;
                                unique (flatten [
                                  buildInputs
                                  nativeBuildInputs
                                  propagatedBuildInputs
                                  propagatedNativeBuildInputs
                                ]);
                              enterShell = v.shellHook;
                            }
                            (preOutputs.devShells.${system}.${name} or { })
                            (plus.devShells.${system}.${name} or { })
                          ];
                        })) devShells)
                    ];
                };
                allOutputs = foldOrFlake mkFlake [
                  (fupRemove preOutputs)
                  (if mkFlake then {
                    channels.${channel} = {
                      ${
                        mif.null (!((plus.channels.${channel} or { }) ? input))
                        "input"
                      } = inputs.${channel} or linputs.${channel};
                      overlaysBuilder = channels:
                        unique (flatten [
                          ((plus.channels.${channel}.overlaysBuilder or (_:
                            [ ])) channels)
                          ((preOutputs.channels.${channel}.overlaysBuilder or (_:
                            [ ])) channels)
                          ((plus.channels.${channel}.overlaysBuilder or (_:
                            [ ])) channels)
                          (attrValues self.overlays)
                        ]);
                    };
                    outputsBuilder = channels:
                      let pkgs = channels.${channel};
                      in fold.merge [
                        (systemOutputs pkgs.stdenv.targetPlatform.system
                          channels pkgs)
                        ((plus.outputsBuilder or (_: { })) channels)
                        ((preOutputs.outputsBuilder or (_: { })) channels)
                        (outputsBuilder channels)
                      ];
                  } else
                    (eachSystem supportedSystems (system:
                      let
                        superpkgs = {
                          inputs = fold.set [
                            (filterAttrs (n: v:
                              (iron.any [
                                (has.prefix n (flatten [
                                  "nixos-"
                                  "nixpkgs-"
                                  (channelNames.prefix or [ ])
                                ]))
                                (has.infix n (channelNames.suffix or [ ]))
                                (has.suffix n (channelNames.suffix or [ ]))
                                (elem n (flatten [
                                  "nixpkgs"
                                  (channelNames.names or [ ])
                                ]))
                              ])
                              && ((v.legacyPackages.x86_64-linux or { }) ? nix))
                              inputs)
                            (mapAttrs (n: getAttr "input")
                              (filterAttrs (n: hasAttr "input") channelConfigs))
                          ];
                          configs = mapAttrs (n: v:
                            fold.merge [
                              { inherit system; }
                              (removeAttrs (channelConfigs.${n} or { }) [
                                "input"
                                "patches"
                              ])
                            ]) superpkgs.inputs;
                          nixpkgs = mapAttrs (n: src:
                            if (((channelConfigs.${n} or { }) ? patches)
                              || patchGlobally) then
                              ((import src
                                superpkgs.configs.${n}).applyPatches {
                                  inherit src;
                                  patches = flatten [
                                    (channelConfigs.${n}.patches or { })
                                    (optionals patchGlobally [

                                    ])
                                  ];
                                  name = "mkOutputPatches";
                                })
                            else
                              src) superpkgs.inputs;
                        };
                        __channels =
                          mapAttrs (n: v: import v superpkgs.configs.${n})
                          superpkgs.nixpkgs;
                        _channels = mapAttrs (N: V:
                          fold.set (mapAttrsToList (n: v: v V V) self.overlays))
                          __channels;
                        channels = mapAttrs
                          (n: mergeAttrs inputs.${n}.legacyPackages.${system})
                          _channels;
                        pkgs = channels.${channel};
                      in fold.set [
                        { inherit superpkgs; }
                        (systemOutputs system channels pkgs)
                      ])))
                  ({
                    overlays = fold.set [

                      # For some reason, the binary cache isn't hit without the following blocks before:
                      # `(removeAttrs bothOverlays [ "__unfix__" "__extend__" ])'
                      # NOTE: The `iron-valiant' prefixes are for ordering purposes:
                      # https://en.wikipedia.org/wiki/ASCII#Printable_characters
                      (optionalAttrs base (listToAttrs (map (pkg:
                        let inputChannel = args.baseChannel or channel;
                        in nameValuePair "!iron-valiant-${pkg}-${inputChannel}"
                        (final: prev:
                          let
                            default =
                              inputs.${inputChannel}.legacyPackages.${prev.targetPlatform.system}.${pkg};
                          in {
                            ${pkg} = default;
                            "${pkg}Packages" = default.pkgs;
                          })) (filter (hasPrefix "python")
                            iron.attrs.packages.python))))

                      # (map (group:
                      #   (mapAttrs' (n: v:
                      #     let
                      #       inputChannel = if (n == "null") then
                      #         (args.baseChannel or channel)
                      #       else
                      #         n;
                      #     in nameValuePair
                      #     "#iron-valiant-${group}-${inputChannel}"
                      #     (iron.update.${group}.replace.inputList.super
                      #       (final: prev:
                      #         inputs.${inputChannel}.legacyPackages.${prev.stdenv.targetPlatform.system})
                      #       (toList v)))
                      #     (iron.getOfficialOverlays group inputs overlayset)))
                      #   (attrNames iron.attrs.versions))

                      (let
                        inputChanneler = n:
                          if (n == "null") then
                            (args.baseChannel or channel)
                          else
                            n;
                      in map (group:
                        (mapAttrsToList (N: V:
                          iron.mapAttrNames (n: v:
                            "#iron-valiant-${group}-${inputChanneler N}-${n}")
                          V) (mapAttrs (n: v:
                            iron.update.${group}.replace.inputList.attrs
                            (final: prev:
                              inputs.${
                                inputChanneler n
                              }.legacyPackages.${prev.stdenv.targetPlatform.system})
                            (toList v)) (iron.getOfficialOverlays group inputs
                              overlayset)))) (attrNames iron.attrs.versions))

                      (mapAttrs' (n: v:
                        let
                          inputChannel = if (n == "null") then
                            (args.baseChannel or channel)
                          else
                            n;
                        in nameValuePair "#iron-valiant-general-${inputChannel}"
                        (final: prev:
                          genAttrs (toList v) (flip getAttr
                            inputs.${inputChannel}.legacyPackages.${prev.stdenv.targetPlatform.system})))
                        (iron.getOfficialOverlays "general" inputs overlayset))

                      (removeAttrs bothOverlays [ "__unfix__" "__extend__" ])

                      (overlayset.preOverlays or { })
                      preOverlays
                      (map (p: libify (p inputs))
                        (attrValues iron.inputPkgsToOverlays))
                      (map (a: a inputs) (attrValues iron.inputAppsToOverlays))
                      (map (o: libify (self.overlayset.${o} or { }))
                        (attrNames iron.attrs.versions))
                      { lib = final: prev: { inherit lib; }; }
                      (mapAttrs (n: v: final: prev:
                        let cpkg = v.package or v;
                        in {
                          ${n} = callPackageFilter final.callPackage cpkg
                            (fold.set [
                              { pname = n; }
                              (args.inheritance or { })
                              (v.inheritance or { })
                            ]);
                        }) self.callPackages)
                      {
                        inherit default;
                        ${pname} = default;
                      }
                      (overlayset.overlays or { })
                    ];
                    defaultOverlay = self.overlays.default;
                    overlay = self.defaultOverlay;
                    callPackage = let e = tryEval callPackage;
                    in if e.success then callPackage else null;
                    callPackages = getCallPackages plus args;
                    mkOutputs = plus.mkOutputs or mkOutputs;
                    inherit lib type group channel doCheck callPackageset
                      overlayset parallel;
                    valiant = true;
                  })
                  (fupRemove plus)
                  (swapSystemOutputs supportedSystems
                    (removeAttrs self supportedSystems))
                ];
              in if (isList languages) then
                (mkLanguage
                  (composeLanguages (map (flip getAttr mkLanguages) languages)))
              else if (isString languages) then
                (mkLanguage (mkLanguages.${languages} plus args))
              else if languages then
                (mkLanguage (composeLanguages (attrValues mkLanguages)))
              else
                allOutputs;
          }
          (mapAttrs (language: v: plus: args:
            mkLanguage (v plus (args // { inherit language; }))) mkLanguages)
        ];
    in base (makeExtensibleWithCustomName "__extend__" (_: { })) { } "nixpkgs"
    lfinal { };

    versionIs = rec {
      # a is older than or equal to b
      ote = a: b: elem (compareVersions a b) [ (0 - 1) 0 ];
      # a is newer than or equal to b
      nte = a: b: elem (compareVersions a b) [ 0 1 ];
    };
    channel = let inherit (iron) fold attrs versionIs has;
    in fold.set [
      (mapAttrs (n: v: v attrs.channel.value) versionIs)
      {
        mus = c: has.suffix c [ "-master" "-unstable" "-small" ];
        musd = c: pkg: default: if (iron.channel.mus c) then pkg else default;
      }
    ];
    changed = let inherit (iron) attrs versionIs;
    in genAttrs (remove "changed" (attrNames attrs.versions))
    (pkg: final: prev: mapAttrs (n: v: v final.${pkg} prev.${pkg}) versionIs);

    getAttrs = list: filterAttrs (n: v: elem n (unique (flatten list)));

    swapSystemOutputs = supportedSystems: attrs:
      let
        swap = system:
          mapAttrs (n: getAttr system) (filterAttrs (n: isAttrsOnly) attrs);
      in if (isString supportedSystems) then {
        ${supportedSystems} = swap supportedSystems;
      } else
        (genAttrs supportedSystems swap);

    multiSplitString = splits: string:
      if splits == [ ] then
        string
      else
        (remove "" (flatten (map (iron.multiSplitString (init splits))
          (splitString (last splits) string))));
    has = {
      prefix = string: any (flip hasPrefix string);
      suffix = string: any (flip hasSuffix string);
      infix = string: any (flip hasInfix string);
    };

    filters = {
      has = {
        attrs = list: attrs:
          let l = unique (flatten list);
          in iron.fold.set [
            (iron.getAttrs l attrs)
            (iron.genAttrNames (filter isDerivation l)
              (drv: drv.pname or drv.name))
            (filter isAttrsOnly l)
          ];
        list = list: attrs: attrValues (iron.filters.has.attrs list attrs);
      };
      keep = let inherit (iron) has dirCon;
      in {
        prefix = keeping: attrs:
          if ((keeping == [ ]) || (keeping == "")) then
            attrs
          else
            (filterAttrs (n: v: has.prefix n (toList keeping)) attrs);
        suffix = keeping: attrs:
          if ((keeping == [ ]) || (keeping == "")) then
            attrs
          else
            (filterAttrs (n: v: has.suffix n (toList keeping)) attrs);
        infix = keeping: attrs:
          if ((keeping == [ ]) || (keeping == "")) then
            attrs
          else
            (filterAttrs (n: v: has.infix n (toList keeping)) attrs);
        elem = keeping: attrs:
          if ((keeping == [ ]) || (keeping == "")) then
            attrs
          else
            (iron.getAttrs (toList keeping) attrs);
        inherit (dirCon.attrs) dirs others files sym unknown;
        readDir = {
          dirs = {
            prefix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "directory") then
                    (has.prefix n (toList keeping))
                  else
                    true) attrs);
            suffix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "directory") then
                    (has.suffix n (toList keeping))
                  else
                    true) attrs);
            infix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "directory") then
                    (has.infix n (toList keeping))
                  else
                    true) attrs);
            elem = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "directory") then
                    (elem n (toList keeping))
                  else
                    true) attrs);
          };
          others = {
            prefix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v != "directory") then
                    (has.prefix n (toList keeping))
                  else
                    true) attrs);
            suffix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v != "directory") then
                    (has.suffix n (toList keeping))
                  else
                    true) attrs);
            infix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v != "directory") then
                    (has.infix n (toList keeping))
                  else
                    true) attrs);
            elem = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v != "directory") then
                    (elem n (toList keeping))
                  else
                    true) attrs);
          };
          files = {
            prefix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "regular") then
                    (has.prefix n (toList keeping))
                  else
                    true) attrs);
            suffix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "regular") then
                    (has.suffix n (toList keeping))
                  else
                    true) attrs);
            infix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "regular") then
                    (has.infix n (toList keeping))
                  else
                    true) attrs);
            elem = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "regular") then (elem n (toList keeping)) else true)
                  attrs);
          };
          sym = {
            prefix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "symlink") then
                    (has.prefix n (toList keeping))
                  else
                    true) attrs);
            suffix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "symlink") then
                    (has.suffix n (toList keeping))
                  else
                    true) attrs);
            infix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "symlink") then
                    (has.infix n (toList keeping))
                  else
                    true) attrs);
            elem = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "symlink") then (elem n (toList keeping)) else true)
                  attrs);
          };
          unknown = {
            prefix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "unknown") then
                    (has.prefix n (toList keeping))
                  else
                    true) attrs);
            suffix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "unknown") then
                    (has.suffix n (toList keeping))
                  else
                    true) attrs);
            infix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "unknown") then
                    (has.infix n (toList keeping))
                  else
                    true) attrs);
            elem = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if (v == "unknown") then (elem n (toList keeping)) else true)
                  attrs);
          };
          static = {
            prefix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if ((v == "regular") || (v == "unknown")) then
                    (has.prefix n (toList keeping))
                  else
                    true) attrs);
            suffix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if ((v == "regular") || (v == "unknown")) then
                    (has.suffix n (toList keeping))
                  else
                    true) attrs);
            infix = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if ((v == "regular") || (v == "unknown")) then
                    (has.infix n (toList keeping))
                  else
                    true) attrs);
            elem = keeping: attrs:
              if ((keeping == [ ]) || (keeping == "")) then
                attrs
              else
                (filterAttrs (n: v:
                  if ((v == "regular") || (v == "unknown")) then
                    (elem n (toList keeping))
                  else
                    true) attrs);
          };
        };
      };
      remove = let inherit (iron) has dirCon;
      in {
        prefix = ignores: filterAttrs (n: v: !(has.prefix n (toList ignores)));
        suffix = ignores: filterAttrs (n: v: !(has.suffix n (toList ignores)));
        infix = ignores: filterAttrs (n: v: !(has.infix n (toList ignores)));
        elem = ignores: flip removeAttrs (toList ignores);
        dirs = dirCon.attrs.others;
        files = filterAttrs (n: v: v != "regular");
        others = dirCon.attrs.dirs;
        sym = filterAttrs (n: v: v != "symlink");
        unknown = filterAttrs (n: v: v != "unknown");
        readDir = {
          dirs = {
            prefix = ignores:
              filterAttrs
              (n: v: (!(has.prefix n (toList ignores))) && (v == "directory"));
            suffix = ignores:
              filterAttrs
              (n: v: (!(has.suffix n (toList ignores))) && (v == "directory"));
            infix = ignores:
              filterAttrs
              (n: v: (!(has.infix n (toList ignores))) && (v == "directory"));
            elem = ignores:
              filterAttrs
              (n: v: (!(elem n (toList ignores))) && (v == "directory"));
          };
          others = {
            prefix = ignores:
              filterAttrs (n: v:
                if (v != "directory") then
                  (!(has.prefix n (toList ignores)))
                else
                  true);
            suffix = ignores:
              filterAttrs (n: v:
                if (v != "directory") then
                  (!(has.suffix n (toList ignores)))
                else
                  true);
            infix = ignores:
              filterAttrs (n: v:
                if (v != "directory") then
                  (!(has.infix n (toList ignores)))
                else
                  true);
            elem = ignores:
              filterAttrs (n: v:
                if (v != "directory") then
                  (!(elem n (toList ignores)))
                else
                  true);
          };
          files = {
            prefix = ignores:
              filterAttrs (n: v:
                if (v == "regular") then
                  (!(has.prefix n (toList ignores)))
                else
                  true);
            suffix = ignores:
              filterAttrs (n: v:
                if (v == "regular") then
                  (!(has.suffix n (toList ignores)))
                else
                  true);
            infix = ignores:
              filterAttrs (n: v:
                if (v == "regular") then
                  (!(has.infix n (toList ignores)))
                else
                  true);
            elem = ignores:
              filterAttrs (n: v:
                if (v == "regular") then
                  (!(elem n (toList ignores)))
                else
                  true);
          };
          sym = {
            prefix = ignores:
              filterAttrs (n: v:
                if (v == "symlink") then
                  (!(has.prefix n (toList ignores)))
                else
                  true);
            suffix = ignores:
              filterAttrs (n: v:
                if (v == "symlink") then
                  (!(has.suffix n (toList ignores)))
                else
                  true);
            infix = ignores:
              filterAttrs (n: v:
                if (v == "symlink") then
                  (!(has.infix n (toList ignores)))
                else
                  true);
            elem = ignores:
              filterAttrs (n: v:
                if (v == "symlink") then
                  (!(elem n (toList ignores)))
                else
                  true);
          };
          unknown = {
            prefix = ignores:
              filterAttrs (n: v:
                if (v == "unknown") then
                  (!(has.prefix n (toList ignores)))
                else
                  true);
            suffix = ignores:
              filterAttrs (n: v:
                if (v == "unknown") then
                  (!(has.suffix n (toList ignores)))
                else
                  true);
            infix = ignores:
              filterAttrs (n: v:
                if (v == "unknown") then
                  (!(has.infix n (toList ignores)))
                else
                  true);
            elem = ignores:
              filterAttrs (n: v:
                if (v == "unknown") then
                  (!(elem n (toList ignores)))
                else
                  true);
          };
          static = {
            prefix = keeping:
              filterAttrs (n: v:
                if ((v == "regular") || (v == "unknown")) then
                  (!(has.prefix n (toList keeping)))
                else
                  true);
            suffix = keeping:
              filterAttrs (n: v:
                if ((v == "regular") || (v == "unknown")) then
                  (!(has.suffix n (toList keeping)))
                else
                  true);
            infix = keeping:
              filterAttrs (n: v:
                if ((v == "regular") || (v == "unknown")) then
                  (!(has.infix n (toList keeping)))
                else
                  true);
            elem = keeping:
              filterAttrs (n: v:
                if ((v == "regular") || (v == "unknown")) then
                  (!(elem n (toList keeping)))
                else
                  true);
          };
        };
      };
    };
    getPyVersion = string:
      pipe (splitString "\n" string) [
        (filter (line:
          iron.has.infix line [
            "'version':"
            ''"version":''
            "version="
            "version ="
            "__version__="
            "__version__ ="
          ]))
        head
        (iron.multiSplitString [ "'" ''"'' ])
        naturalSort
        head
      ];
    # TODO: Implement the formats from here: https://github.com/NixOS/nixpkgs/blob/master/pkgs/development/interpreters/python/mk-python-derivation.nix#L81
    pyVersion = src:
      let
        formats = {
          pyproject = rec {
            file = "${src}/pyproject.toml";
            imported = importTOML file;
          };
          setup = rec {
            files = filter pathExists
              (map (p: "${src}/${p}") [ "setup.py" "setup.cfg" ]);
            file = head files;
            imported = readFile file;
          };
        };
      in if (iron.all [
        (pathExists formats.pyproject.file)
        (formats.pyproject.imported ? tool)
        (formats.pyproject.imported.tool ? poetry)
      ]) then
        formats.pyproject.imported.tool.poetry.version
      else if (formats.setup.files != [ ]) then
        (iron.getPyVersion formats.setup.imported)
      else
        (iron.getPyVersion (readFile src));

    readFileExists = file: optionalString (pathExists file) (readFile file);
    readDirExists = dir: optionalAttrs (pathExists dir) (readDir dir);
    dirCon = let
      ord = func: dir:
        filterAttrs func
        (if (isAttrsOnly dir) then dir else (iron.readDirExists dir));
    in rec {
      attrs = {
        dirs = ord (n: v: v == "directory");
        others = ord (n: v: v != "directory");
        files = ord (n: v: v == "regular");
        sym = ord (n: v: v == "symlink");
        unknown = ord (n: v: v == "unknown");
      };
      dirs = dir: attrNames (attrs.dirs dir);
      others = dir: attrNames (attrs.others dir);
      files = dir: attrNames (attrs.files dir);
      sym = dir: attrNames (attrs.sym dir);
      unknown = dir: attrNames (attrs.unknown dir);
    };

    recursiveUpdateAllStrings = recursiveUpdateAll "\n";

    fold = let
      folders = {
        set = list:
          foldr mergeAttrs { } (let _ = flatten list;
          in if (any isFunction _) then
            (trace _ (abort "Sorry; a wild function appeared!"))
          else
            _);
        recursive = list:
          foldr recursiveUpdate { } (let _ = flatten list;
          in if (any isFunction _) then
            (trace _ (abort "Sorry; a wild function appeared!"))
          else
            _);
        merge = list:
          foldr (recursiveUpdateAll null) { } (if (any isFunction list) then
            (trace list (abort "Sorry; a wild function appeared!"))
          else
            list);
        stringMerge = list:
          foldr iron.recursiveUpdateAllStrings { }
          (if (any isFunction list) then
            (trace list (abort "Sorry; a wild function appeared!"))
          else
            list);
      };
      inherit (iron) filters;
    in folders.set [
      folders
      {
        # Adapted From: https://gist.github.com/adisbladis/2a44cded73e048458a815b5822eea195
        shell = pkgs: envs:
          foldr (new: old:
            pkgs.mkShell {
              buildInputs =
                filters.has.list [ new.buildInputs old.buildInputs ] pkgs;
              nativeBuildInputs =
                filters.has.list [ new.nativeBuildInputs old.nativeBuildInputs ]
                pkgs;
              propagatedBuildInputs = filters.has.list [
                new.propagatedBuildInputs
                old.propagatedBuildInputs
              ] pkgs;
              propagatedNativeBuildInputs = filters.has.list [
                new.propagatedNativeBuildInputs
                old.propagatedNativeBuildInputs
              ] pkgs;
              shellHook = new.shellHook + "\n" + old.shellHook;
            }) (pkgs.mkShell { })
          (map (e: if (isAttrsOnly e) then (pkgs.mkShell e) else e)
            (flatten envs));
        debug = mapAttrs (n: v: list: v (traceVal (flatten list))) folders;
        deebug =
          mapAttrs (n: v: list: v (iron.traceValSeq (flatten list))) folders;
      }
    ];

    dontCheck = old: {
      doCheck = false;
      pythonImportsCheck = [ ];
      postCheck = "";
      checkPhase = "";
      doInstallCheck = false;
      ${
        if (hasInfix ''"(progn (add-to-list 'load-path \"$LISPDIR\")''
          (old.postInstall or "")) then
          "postInstall"
        else
          null
      } = "";
    };

    functors.xelf = { __functor = self: x: let xelf = x self; in x xelf; };

    mkPythonPackage = { self, inputs ? { }, package, recursiveOverrides ? [ ] }:
      pkgs@{ mount, python, pythonOlder, poetry-core, setuptools, wheel, rich
      , makePythonPath, buildPythonPackage, hy, hyrule, ... }:
      let
        inherit (iron) functors filters fold pyVersion mkCheckInputs;
        pname = package.pname or self.pname;
        owner = package.owner or "syvlorg";

        # `pkgs' overrides `python.pkgs' because the packages in `pkgs'
        # can be different from the ones in `python.pkgs'
        ppkgs = python.pkgs // pkgs;
        format = package.format or toOverride.format;
        formatIsSetuptools = format == "setuptools";
        formatIsPyproject = format == "pyproject";
        toOverride = {
          inherit pname;
          doCheck = true;
          disabled = pythonOlder "3.9";
          format = "pyproject";
          version = pyVersion package.src;

          # TODO
          # ${if formatIsSetuptools then "buildPhase" else null} =
          #   "${interpreter} setup.py bdist_wheel";

        };
        overrideNames = attrNames toOverride;
        pselfOverride = iron.getAttrs overrideNames package;
        absolute = removeAttrs (let
          a = functors.xelf (alf:
            mapAttrs (n: v: unique (flatten [ v (package.${n} or [ ]) ])) {
              buildInputs = [
                (optional formatIsPyproject poetry-core)
                (optionals formatIsSetuptools [ setuptools wheel ])
              ];
              nativeBuildInputs = alf.buildInputs;
              propagatedBuildInputs = filters.has.list [
                rich
                (optionals (self.type == "hy") [ hy hyrule ])
                (optionals (inputs != { })
                  (iron.inputPkgsToPackages.python inputs))
              ] ppkgs;
              propagatedNativeBuildInputs = alf.propagatedBuildInputs;
            });
        in fold.set [
          a

          # TODO: Is this still necessary?
          (rec {
            checkInputs = let
              propagatedNativeBuildInputNames =
                map (pkg: pkg.pname or pkg.name) a.propagatedNativeBuildInputs;
            in map (pkg:
              (pkg.overridePythonAttrs or (f: pkg)) (old:
                genAttrs [
                  "propagatedBuildInputs"
                  "propagatedNativeBuildInputs"
                ] (p:
                  filter (i:
                    !(elem (i.pname or i.name) propagatedNativeBuildInputNames))
                  (old.${p} or [ ])))) (filters.has.list [
                    "pytestCheckHook"
                    (mkCheckInputs.python { inherit (self) type parallel; })
                    (package.checkInputs or [ ])
                  ] ppkgs);

            nativeCheckInputs =
              flatten [ checkInputs (package.nativeCheckInputs or [ ]) ];
          })
        ]) recursiveOverrides;
        absoluteNames = attrNames absolute;
        toRecurse = removeAttrs (rec {

          # Adapted From: https://nixos.org/manual/nixpkgs/stable/#:~:text=roughly%20translates%20to%3A
          # And: https://discourse.nixos.org/t/get-pythonpath-from-pkgs-python3-withpackages/6076/2
          postCheck = ''
            PYTHONPATH=${
              makePythonPath (flatten [
                absolute.propagatedNativeBuildInputs
                (package.propagatedNativeBuildInputs or [ ])
              ])
            }:$PYTHONPATH
            python -c "import ${
              replaceStrings [ "-" ] [ "_" ] (concatStringsSep "; import "
                (flatten [ pname (package.pythonImportsCheck or [ ]) ]))
            }"
          '';

          pytestFlagsArray = flatten [
            "--strict-markers"
            "--suppress-no-test-exit-code"
            (optionals self.parallel [ "-n" "auto" "--dist" "loadgroup" ])
          ];
          passthru = {
            format = package.format or toOverride.format;
            disabled = package.disabled or toOverride.disabled;
          };
          meta = {
            homepage = "https://github.com/${owner}/${pname}";

            # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/pkgs/stdenv/generic/make-derivation.nix#L134-L139
            position = let pos = unsafeGetAttrPos "pname" package;
            in "${pos.file}:${toString pos.line}";

          };
        }) recursiveOverrides;
        recursiveNames = attrNames toOverride;
        pselfRecursed = iron.getAttrs recursiveNames package;
      in buildPythonPackage (fold.set [
        absolute
        toOverride
        pselfOverride
        (fold.stringMerge [ toRecurse pselfRecursed ])
        (removeAttrs package (flatten [
          overrideNames
          recursiveNames
          absoluteNames
          "owner"
          "pythonImportsCheck"
        ]))
      ]);

    toPythonApplication = extras': pname:
      { stdenv, python3Packages, python3, bc }:
      let
        ppkgs = python3Packages;
        extras = if (isFunction extras') then
          (extras' stdenv.targetPlatform.system)
        else
          extras';
      in ppkgs.buildPythonApplication (iron.fold.stringMerge [
        ppkgs.${pname}.passthru
        (let
          appSrc = extras.appSrc or (pname + "/"
            + (if (pathExists "${ppkgs.${pname}.src}/${pname}/__main__.py") then
              "__main__.py"
            else
              "__init__.py"));
          outputs = map (o: "$out/bin/" + o)
            (flatten [ (extras.appAliases or [ ]) (extras.appName or pname) ]);
        in rec {
          inherit pname;
          inherit (ppkgs.${pname}) version src passthru;

          # Adapted From:
          # Answer: https://stackoverflow.com/a/57230822/10827766
          # User: https://stackoverflow.com/users/3574379/srghma
          # ${if (pname == libName) then null else "pythonOutputDistPhase"} = ":";
          # pythonOutputDistPhase = ":";

          # Adapted From: https://github.com/NixOS/nixpkgs/blob/master/pkgs/development/interpreters/python/hooks/setuptools-check-hook.sh
          # This is `nix_run_setup': https://github.com/NixOS/nixpkgs/blob/master/pkgs/development/interpreters/python/run_setup.py
          setuptoolsCheckPhase = ''
            echo "Executing setuptoolsCheckPhase"
            runHook preCheck

            cp -f ${linputs.nixpkgs}/pkgs/development/interpreters/python/run_setup.py nix_run_setup
            ${python3.interpreter} nix_run_setup test || :

            runHook postCheck
            echo "Finished executing setuptoolsCheckPhase"
          '';

          propagatedBuildInputs = toList ppkgs.${pname};
          propagatedNativeBuildInputs = propagatedBuildInputs;
          installPhase = extras.aself.installPhase or ''
            mkdir --parents $out/bin
            ${concatMapStringsSep "\n"
            (o: "cp $src/${appSrc} ${o}; chmod +x ${o}") outputs}
          '';

          # Adapted From:
          # Answer: https://stackoverflow.com/a/17794626/10827766
          # User: https://stackoverflow.com/users/360496/yossi-farjoun
          postFixup = ''
            ${concatMapStringsSep "\n" (o: "wrapProgram ${o} $makeWrapperArgs")
            outputs}
          '' + (optionalString (any id [
            ((extras ? global) && (extras.global ? shellHook))
            (extras ? appShellHook)
          ]) ''
            # ''${pname} --> .''${pname}-wrapped_ --> .''${pname}-wrapped
            dd if=/dev/null \
               of=$out/bin/.${pname}-wrapped_ \
               bs=1 \
               seek=$(echo $(stat --format=%s $out/bin/.${pname}-wrapped_ ) - $( tail -n1 $out/bin/.${pname}-wrapped_ | wc -c) | ${bc}/bin/bc )
            cat <<- "49b879865ad941f2ba20b63599e596e7" >> $out/bin/.${pname}-wrapped_
            ${extras.global.shellHook or ""}
            ${extras.appShellHook or ""}
            49b879865ad941f2ba20b63599e596e7
            echo -n 'exec -a "$0" "' >> $out/bin/.${pname}-wrapped_
            echo -n "$out/bin/.${pname}-wrapped" >> $out/bin/.${pname}-wrapped_
            echo -n '" "$@"' >> $out/bin/.${pname}-wrapped_
          '');

          makeWrapperArgs = flatten [

            # Adapted From: https://discourse.nixos.org/t/get-pythonpath-from-pkgs-python3-withpackages/6076/2
            "--prefix PYTHONPATH : ${
              ppkgs.makePythonPath propagatedNativeBuildInputs
            }"

            # Adapted From: https://gist.github.com/CMCDragonkai/9b65cbb1989913555c203f4fa9c23374
            (optional (extras.appPathUseBuildInputs or false)
              "--prefix PATH : ${
                makeBinPath (ppkgs.${pname}.buildInputs or [ ])
              }")
            (optional (extras.appPathUseNativeBuildInputs or false)
              "--prefix PATH : ${
                makeBinPath (ppkgs.${pname}.nativeBuildInputs or [ ])
              }")

          ];
        })
        (removeAttrs (extras.aself or { }) [ "installPhase" ])
      ]);

    fpipe = pipe-list: flip pipe (flatten pipe-list);
    removeFix = let sortFunc = sort (a: b: (length a) > (length b));
    in rec {
      default = func: fixes: iron.fpipe (map func (sortFunc fixes));
      prefix = default removePrefix;
      suffix = default removeSuffix;
      infix = fixes:
        replaceStrings (sortFunc fixes) (genList (i: "") (length fixes));
    };
    extendInputs = inputs: lockfile':
      (makeExtensible (_: inputs)).extend (final: prev:
        recursiveUpdate prev (mapAttrs (n: v:
          let
            inherit (iron) fold removeFix;
            vo = v.original or { ref = null; };
            vl = v.locked or { rev = null; };
          in fold.set [
            vl
            vo
            {
              version = if (vo ? ref) then
                (removeFix.prefix [ "v" ] vo.ref)
              else
                vl.rev;
            }
          ]) lockfile'.nodes));
    mif = {
      list = optionals;
      list' = optional;
      set = optionalAttrs;
      num = condition: value: if condition then value else 0;
      null = condition: value: if condition then value else null;
      str = optionalString;
      True = condition: value: if condition then value else true;
      False = condition: value: if condition then value else false;
      fn = condition: fn: value: if condition then (fn value) else value;
    };
    mifNotNull = {
      default = a: b: if (a != null) then a else b;
      list = a: optionals (a != null);
      list' = a: optional (a != null);
      set = a: optionalAttrs (a != null);
      num = a: b: if (a != null) then b else 0;
      null = a: b: if (a != null) then b else null;
      nullb = a: b: c: if (a != null) then b else c;
      str = a: optionalString (a != null);
      True = a: b: if (a != null) then b else true;
      False = a: b: if (a != null) then b else false;
    };

    getPkg = let inherit (iron) attrs;
    in {
      python = channel: flip getAttr channel.${attrs.versions.python}.pkgs;
    };

    update = {
      # Adapted From: https://discourse.nixos.org/t/how-to-add-custom-python-package/536/4
      # And: https://discourse.nixos.org/t/use-multiple-instances-of-prev-python-override/20066/2
      python = {
        python = attrs: final: prev:
          let
            default' = pythonVersion:
              prev.${pythonVersion}.override (super: {
                stdenv =
                  linputs.nixpkgs.legacyPackages.${prev.stdenv.targetPlatform.system}.gccStdenv;
                self = final.${pythonVersion};
                pythonAttr = pythonVersion;
                packageOverrides =
                  composeExtensions (super.packageOverrides or (_: _: { }))
                  (if (isFunction attrs) then attrs else (new: old: attrs));
              });
            # Adapted From: https://github.com/NixOS/nixpkgs/issues/44426#issuecomment-1223613633
            # And: https://github.com/NixOS/nixpkgs/issues/44426#issuecomment-1338223044
            # prev.${pythonVersion} // {
            #   pkgs = prev.${pythonVersion}.pkgs.overrideScope
            #     (if (isFunction attrs) then attrs else (new: old: attrs));
            # };
            default = default' iron.attrs.versions.python;
          in iron.fold.set [
            (map (pkg: {
              ${pkg} = default;
              "${pkg}Packages" = default.pkgs;
            }) (filter (hasPrefix "python") iron.attrs.packages.python))
            {
              pypy3 = default' "pypy3";
              pypy3Packages = final.pypy3.pkgs;
              hy = final.python3Packages.toPythonApplication
                final.python3Packages.hy;
              pythons = getAttrs iron.attrs.packages.python final;
            }
          ];
        replace = let
          inherit (iron) getPkg fold mif channel;
          replacements = {
            package = name: value:
              iron.update.python.python (new: old: {
                ${name} = if (isFunction value) then (value new old) else value;
              });
            module = name: value:
              iron.update.python.python (new: old: {
                ${name} = new.toPythonModule
                  (if (isFunction value) then (value new old) else value);
              });
            input = name: channel:
              replacements.package name (getPkg.python channel name);
            inputList = {
              attrs = channel:
                flip genAttrs (pkg: final: prev:
                  replacements.input pkg (if (isFunction channel) then
                    (channel final prev)
                  else
                    channel) final prev);
              list = channel: list:
                attrValues (replacements.inputList.attrs channel list);
              super = channel: list: final: prev:
                iron.update.python.python (genAttrs list (getPkg.python
                  (if (isFunction channel) then
                    (channel final prev)
                  else
                    channel))) final prev;
            };
            override = name: channel: inputs: func: final: prev:
              replacements.package name
              ((getPkg.python channel name).overridePythonAttrs func) final
              prev;
          };
        in fold.set [
          replacements
          {
            channel = let
              channelReplacements = {
                ote = mapAttrs
                  (n: v: c1: c2: name: v (mif.null (channel.ote c1 c2) name))
                  replacements;
                nte = mapAttrs
                  (n: v: c1: c2: name: v (mif.null (channel.nte c1 c2) name))
                  replacements;
              };
            in fold.set [
              channelReplacements
              (mapAttrs' (N: V:
                nameValuePair ("c" + N)
                (mapAttrs (n: v: v iron.attrs.channel.value) V))
                channelReplacements)
            ];
          }
        ];
        callPython = inheritance: name: pkg:
          iron.update.python.python (new: old: {
            ${name} = iron.callPackageFilter new.callPackage pkg inheritance;
          });
        callPythonFile = inheritance: file:
          iron.update.python.python (new: old: {
            ${imports.name { inherit file; }} =
              new.callPackage file inheritance;
          });
        package = pkg: func:
          iron.update.python.python (new: old: {
            ${pkg} = old.${pkg}.overridePythonAttrs (func new old);
          });
        packages = dir: final:
          iron.update.python.python (imports.set {
            call = final.python3Pkgs;
            inherit dir;
            ignores.elem = iron.dirCon.dirs dir;
          }) final;
      };
    };

  });
}
