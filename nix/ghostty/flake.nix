{
  description = "libghostty-vt — Ghostty terminal emulation library for clamor";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    ghostty-src = {
      url = "github:ghostty-org/ghostty/bebca84668947bfc92b9a30ed58712e1c34eee1d";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      ghostty-src,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          inherit (pkgs) lib stdenv;

          deps = pkgs.callPackage "${ghostty-src}/build.zig.zon.nix" {
            linkFarm =
              name: entries:
              pkgs.runCommand name { } ''
                mkdir -p $out
                ${lib.concatMapStringsSep "\n" (e: ''
                  cp -rL ${e.path} $out/${e.name}
                '') entries}
              '';
          };

          libghostty-vt = stdenv.mkDerivation {
            pname = "libghostty-vt";
            version = "0.1.0";

            src = ghostty-src;

            nativeBuildInputs =
              [
                pkgs.git
                pkgs.pkg-config
                pkgs.zig_0_15
              ]
              ++ lib.optionals stdenv.isDarwin [
                pkgs.darwin.cctools
                pkgs.fixDarwinDylibNames
                pkgs.xcbuild
              ];

            dontConfigure = true;
            dontSetZigDefaultFlags = true;

            buildPhase = ''
              runHook preBuild

              export ZIG_GLOBAL_CACHE_DIR="$TMPDIR/zig-global"
              export ZIG_LOCAL_CACHE_DIR="$TMPDIR/zig-local"
              mkdir -p "$ZIG_GLOBAL_CACHE_DIR" "$ZIG_LOCAL_CACHE_DIR"

              zig build \
                --system ${deps} \
                -Demit-lib-vt=true \
                -Dcpu=baseline \
                -Doptimize=ReleaseFast \
                -Dapp-runtime=none \
                --prefix $out \
                ${lib.optionalString stdenv.isDarwin "-Demit-xcframework=false"}

              runHook postBuild
            '';

            installPhase = ''
              runHook preInstall
              runHook postInstall
            '';

            doCheck = false;

            meta = {
              description = "Ghostty terminal emulation library";
              license = lib.licenses.mit;
              platforms = lib.platforms.unix;
            };
          };
        in
        {
          default = libghostty-vt;
          inherit libghostty-vt;
        }
      );
    };
}
