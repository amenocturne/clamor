{
  description = "clamor - terminal multiplexer for managing multiple coding agents";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    libghostty-vt = {
      url = "path:./nix/ghostty";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      libghostty-vt,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      cargoToml = nixpkgs.lib.importTOML ./Cargo.toml;

      mkClamor =
        pkgs: ghosttyLib:
        let
          inherit (pkgs) lib stdenv;
          rustTarget = stdenv.hostPlatform.rust.rustcTarget;
        in
        pkgs.rustPlatform.buildRustPackage {
          pname = cargoToml.package.name;
          version = cargoToml.package.version;

          src = lib.cleanSourceWith {
            src = ./.;
            filter =
              path: type:
              let
                base = baseNameOf (toString path);
              in
              !(lib.hasSuffix ".png" base) && base != "target" && base != "tmp" && base != "TODO.md";
          };

          cargoLock.lockFile = ./Cargo.lock;

          nativeBuildInputs = [ pkgs.pkg-config ];
          buildInputs =
            [ ghosttyLib ]
            ++ lib.optionals stdenv.isDarwin [
              pkgs.apple-sdk
              pkgs.libiconv
            ];

          postPatch = ''
            mkdir -p .cargo
            cat >> .cargo/config.toml <<EOF
            [target."${rustTarget}".ghostty-vt]
            rustc-link-lib = ["dylib=ghostty-vt"]
            rustc-link-search = ["native=${ghosttyLib}/lib"]
            EOF
          '';

          # The integration tests spawn real PTYs and rely on a writable HOME;
          # they are not hermetic enough for the sandboxed build. Run them
          # locally with `cargo test`.
          doCheck = false;

          meta = {
            description = cargoToml.package.description;
            homepage = cargoToml.package.repository;
            license = lib.licenses.mit;
            mainProgram = "clamor";
            platforms = lib.platforms.unix;
          };
        };
    in
    {
      packages = forAllSystems (
        system:
        let
          clamor = mkClamor nixpkgs.legacyPackages.${system} libghostty-vt.packages.${system}.default;
        in
        {
          default = clamor;
          clamor = clamor;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/clamor";
        };
      });

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.pkg-config
              pkgs.rustup
              pkgs.rust-analyzer
              pkgs.zig_0_15
            ]
            ++ pkgs.lib.optionals pkgs.stdenv.isDarwin [
              pkgs.apple-sdk
              pkgs.libiconv
            ];
          };
        }
      );

      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixfmt-rfc-style);

      homeManagerModules = {
        default = import ./nix/home-manager-module.nix;
        clamor = import ./nix/home-manager-module.nix;
      };
    };
}
