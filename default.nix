with import <nixpkgs> {};

stdenv.mkDerivation {
  name = "python2-with-packages";

  buildInputs = [
    python3
    python2
    python2Packages.pip
    python2Packages.setuptools
    python2Packages.pytest
	];
}
