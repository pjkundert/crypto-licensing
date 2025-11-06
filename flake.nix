{
  description = "Crypto Licensing development environment with multiple Python versions";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Create Python environments with required packages
        mkPythonEnv = pythonPkg: pythonPkg.withPackages (ps: with ps; [
          pytest
          pip
        ]);

        python39Env = mkPythonEnv pkgs.python39;
        python310Env = mkPythonEnv pkgs.python310;
        python311Env = mkPythonEnv pkgs.python311;
        python312Env = mkPythonEnv pkgs.python312;
        python313Env = mkPythonEnv pkgs.python313;
        pypy310Env = pkgs.pypy310.withPackages (ps: with ps; [
          pytest
        ]);

      in {
        # Single development shell with all Python versions
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Common tools
            cacert
            git
            gnumake
            openssh
            bash
            bash-completion
            which

            # All Python versions with packages
           #python39Env
           #python310Env
            python311Env
            python312Env
            python313Env
           #pypy310Env
          ];

          shellHook = ''
            echo "Welcome to the Crypto Licensing multi-Python development environment!"
            echo "Available Python interpreters:"
            echo "  python:     $(python     --version 2>/dev/null || echo 'not available')"
            echo "  python3.9:  $(python3.9  --version 2>/dev/null || echo 'not available')"
            echo "  python3.10: $(python3.10 --version 2>/dev/null || echo 'not available')"
            echo "  python3.11: $(python3.11 --version 2>/dev/null || echo 'not available')"
            echo "  python3.12: $(python3.12 --version 2>/dev/null || echo 'not available')"
            echo "  python3.13: $(python3.13 --version 2>/dev/null || echo 'not available')"
            echo "  pypy3.10:   $(pypy3.10   --version 2>/dev/null || echo 'not available')"
            echo ""
            echo "All versions have pytest and pip installed."
            echo ""
            echo "Use 'make test' to run tests with the default Python version."
          '';
        };

        # Individual development shells for specific Python versions
        devShells.py39 = pkgs.mkShell {
          buildInputs = [
            pkgs.cacert
            pkgs.git
            pkgs.gnumake
            pkgs.openssh
            pkgs.bash
            pkgs.bash-completion

            python39Env
          ];
          shellHook = ''
            echo "Python 3.9 environment"
          '';
        };

        devShells.py310 = pkgs.mkShell {
          buildInputs = [
            pkgs.cacert
            pkgs.git
            pkgs.gnumake
            pkgs.openssh
            pkgs.bash
            pkgs.bash-completion

            python310Env
          ];
          shellHook = ''
            echo "Python 3.10 environment"
          '';
        };

        devShells.py311 = pkgs.mkShell {
          buildInputs = [
            pkgs.cacert
            pkgs.git
            pkgs.gnumake
            pkgs.openssh
            pkgs.bash
            pkgs.bash-completion

            python311Env
          ];
          shellHook = ''
            echo "Python 3.11 environment"
          '';
        };

        devShells.py312 = pkgs.mkShell {
          buildInputs = [
            pkgs.cacert
            pkgs.git
            pkgs.gnumake
            pkgs.openssh
            pkgs.bash
            pkgs.bash-completion

            python312Env
          ];
          shellHook = ''
            echo "Python 3.12 environment"
          '';
        };

        devShells.py313 = pkgs.mkShell {
          buildInputs = [
            pkgs.cacert
            pkgs.git
            pkgs.gnumake
            pkgs.openssh
            pkgs.bash
            pkgs.bash-completion

            python313Env
          ];
          shellHook = ''
            echo "Python 3.13 environment"
          '';
        };

        devShells.pypy310 = pkgs.mkShell {
          buildInputs = [
            pkgs.which
            pkgs.cacert
            pkgs.git
            pkgs.gnumake
            pkgs.openssh
            pkgs.bash
            pkgs.bash-completion

            pypy310Env
          ];
          shellHook = ''
            echo "PyPy 3.10 environment"
          '';
        };
      });
}
