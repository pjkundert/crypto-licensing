{ pkgs ? import ./nixpkgs.nix {} }:

with pkgs;

let
in
{
  crypto_licensing = stdenv.mkDerivation rec {
    name = "python3-with-pytest";

    buildInputs = [
      git
      openssh
      python312
      python312Packages.pytest
    ];
  };

  crypto_licensing_py313 = stdenv.mkDerivation rec {
    name = "python313-with-pytest";

    buildInputs = [
      git
      openssh
      python313
      python313Packages.pytest
    ];
  };

  crypto_licensing_py27 = stdenv.mkDerivation rec {
    name = "python27-with-pytest";

    buildInputs = [
      git
      openssh
      python27
      python27Packages.pytest
      python27Packages.pip
    ];
  };
}
