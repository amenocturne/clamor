{ config, lib, pkgs, ... }:
let
  cfg = config.programs.clamor;
  yaml = pkgs.formats.yaml { };
in
{
  options.programs.clamor = {
    enable = lib.mkEnableOption "clamor terminal multiplexer";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The clamor package to use.";
    };

    folders = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          path = lib.mkOption {
            type = lib.types.str;
            description = "Absolute or ~ path to the folder.";
          };
          backends = lib.mkOption {
            type = lib.types.listOf lib.types.str;
            description = "Backend IDs this folder may use.";
          };
        };
      });
      default = { };
      description = "Folders managed by clamor, keyed by folder ID.";
    };

    backends = lib.mkOption {
      type = lib.types.attrsOf lib.types.anything;
      default = { };
      description = "Backend definitions keyed by backend ID.";
    };

    dashboard = lib.mkOption {
      type = lib.types.attrsOf lib.types.anything;
      default = { };
      description = "Dashboard settings (watch_mode, etc.).";
    };

    theme = lib.mkOption {
      type = lib.types.attrsOf lib.types.anything;
      default = { };
      description = "Theme overrides.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    xdg.configFile."clamor/config.yaml".source = yaml.generate "clamor-config.yaml" (
      lib.filterAttrs (_: v: v != { }) {
        inherit (cfg) folders backends dashboard theme;
      }
    );
  };
}
