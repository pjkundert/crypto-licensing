{ pkgs ? import ./nixpkgs.nix {} }:

let
  targets = import ./default.nix {
    inherit pkgs;
  };
  targeted = builtins.getEnv "TARGET";
  selected = targeted + pkgs.lib.optionalString (targeted == "") "crypto_licensing";
in

with pkgs;

mkShell {
  buildInputs = lib.getAttrFromPath [ selected "buildInputs" ] targets;

  shellHook = ''
    echo "Welcome to the Python ${selected} environment!"
  '';
}
