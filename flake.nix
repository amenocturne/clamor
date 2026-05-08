{
  description = "clamor - terminal multiplexer for managing multiple coding agents";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  outputs =
    { self, nixpkgs }:
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
        pkgs:
        let
          inherit (pkgs) lib stdenv;
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
              !(lib.hasSuffix ".png" base)
              && base != "target"
              && base != "tmp"
              && base != "TODO.md";
          };

          cargoLock.lockFile = ./Cargo.lock;

          nativeBuildInputs = [ pkgs.pkg-config ];
          buildInputs = lib.optionals stdenv.isDarwin [
            pkgs.apple-sdk
            pkgs.libiconv
          ];

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
          clamor = mkClamor nixpkgs.legacyPackages.${system};
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
            inputsFrom = [ self.packages.${system}.default ];
            packages = [
              pkgs.cargo
              pkgs.rustc
              pkgs.rustfmt
              pkgs.clippy
              pkgs.rust-analyzer
            ];
          };
        }
      );

      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixfmt-rfc-style);
    };
}
