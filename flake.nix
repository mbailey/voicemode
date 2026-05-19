{
  description = "Voice Mode - Natural voice conversations for AI assistants";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # nixos-24.05 is the last channel with cudaPackages_11_8 and gcc11.
    # CUDA 11.8 supports compute 3.5–8.9, covering Pascal (GTX 10xx) through
    # Ada Lovelace (RTX 40xx). Both cudaPackages_11_8 and gcc11 have been
    # removed from nixos-unstable, so we need a second nixpkgs input.
    nixpkgs-cuda11.url = "github:NixOS/nixpkgs/nixos-24.05";

    # Pinned to the latest stable release tag, not main.
    whisper-cpp-src = {
      url = "github:ggerganov/whisper.cpp/v1.8.3";
      flake = false;
    };
  };
  outputs = { self, nixpkgs, flake-utils, nixpkgs-cuda11, whisper-cpp-src }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        lib = pkgs.lib;

        isLinuxX86 = system == "x86_64-linux";

        # CUDA 11.8 toolchain — only instantiated on x86_64-linux.
        # GCC 11 is required because CUDA 11.8's nvcc rejects GCC >= 12.
        # Uses import (not legacyPackages) so we can set allowUnfree for
        # the CUDA redistribution packages without affecting the main pkgs.
        pkgsCuda11 = import nixpkgs-cuda11 {
          inherit system;
          config.allowUnfree = true;
        };

        whisperVersion = "1.8.3";

        # ------------------------------------------------------------------
        # whisper.cpp builder
        # ------------------------------------------------------------------
        #
        # Compute capability reference (set cudaArch to match your GPU):
        #   Pascal  (GTX 10xx)       → "61"
        #   Volta   (Tesla V100)     → "70"
        #   Turing  (RTX 20xx)       → "75"
        #   Ampere  (RTX 30xx)       → "86"
        #   Ada     (RTX 40xx)       → "89"
        #
        # The build sandbox has no GPU, so CMAKE_CUDA_ARCHITECTURES must be
        # set explicitly — auto-detection would fail.
        buildWhisperCpp = {
          cudaSupport ? false,
          cudaArch ? "61", # Pascal default — override for your GPU
          cudaPackages ? pkgsCuda11.cudaPackages_11_8,
          hostCompiler ? pkgsCuda11.gcc11,
        }: pkgs.stdenv.mkDerivation {
          pname = "whisper-cpp" + lib.optionalString cudaSupport "-cuda";
          version = whisperVersion;
          src = whisper-cpp-src;

          nativeBuildInputs = [ pkgs.cmake pkgs.pkg-config ]
            ++ lib.optionals cudaSupport [
              cudaPackages.cuda_nvcc

              # Adds an RPATH entry so libcuda.so.1 (the userspace driver)
              # resolves at runtime. The driver lives outside the nix store
              # (/run/opengl-driver/lib on NixOS) and is not available during
              # the build. autoPatchelfHook is intentionally omitted — it
              # clobbers the driver RPATH, and cmake already handles library
              # references correctly for source builds.
              pkgs.autoAddDriverRunpath
            ];

          buildInputs = lib.optionals cudaSupport [
            cudaPackages.cuda_cudart
            cudaPackages.cuda_cccl   # CUB + Thrust headers
            cudaPackages.libcublas
            # libstdc++ from the host compiler — the CUDA runtime links against it.
            (lib.getLib hostCompiler.cc)
          ];

          cmakeFlags = lib.optionals cudaSupport [
            "-DGGML_CUDA=ON"
            "-DCMAKE_CUDA_ARCHITECTURES=${cudaArch}"
            "-DCMAKE_C_COMPILER=${hostCompiler}/bin/gcc"
            "-DCMAKE_CXX_COMPILER=${hostCompiler}/bin/g++"
          ];

          # libcuda.so.1 is the userspace driver — only present on the host,
          # never in the build sandbox. autoAddDriverRunpath handles runtime
          # resolution via /run/opengl-driver/lib RPATH entry.

          meta = {
            description = "whisper.cpp speech-to-text engine"
              + lib.optionalString cudaSupport " (CUDA, compute ${cudaArch})";
            homepage = "https://github.com/ggerganov/whisper.cpp";
            license = lib.licenses.mit;
            platforms = [ "x86_64-linux" ]
              ++ lib.optionals (!cudaSupport) [ "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
          };
        };

        # ------------------------------------------------------------------
        # whisper-cpp package variants
        # ------------------------------------------------------------------
        whisper-cpp = buildWhisperCpp { };
        whisper-cpp-cuda = buildWhisperCpp { cudaSupport = true; };

        pythonEnv = pkgs.python312.withPackages (ps: with ps; [
          pip
          setuptools
          wheel
          virtualenv
        ]);
        
        # Wrapper script that uses uvx with proper environment.
        # When whisperPackage is set, its bin/ is added to PATH so that
        # VoiceMode's find_whisper_server() discovers whisper-server
        # via `which`.
        mkVoiceMode = { whisperPackage ? null }: pkgs.writeShellScriptBin "voice-mode" ''
          export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
            pkgs.portaudio
            pkgs.libpulseaudio
            pkgs.alsa-lib
            pkgs.stdenv.cc.cc.lib
          ]}:$LD_LIBRARY_PATH"
          
          # Add build-time dependencies for compilation
          export PKG_CONFIG_PATH="${pkgs.lib.makeSearchPathOutput "dev" "lib/pkgconfig" [
            pkgs.alsa-lib
            pkgs.portaudio
            pkgs.libpulseaudio
          ]}:$PKG_CONFIG_PATH"
          
          # Add development headers to C include path
          export CPATH="${pkgs.lib.makeSearchPathOutput "dev" "include" [
            pkgs.alsa-lib
            pkgs.portaudio
            pkgs.libpulseaudio
          ]}:$CPATH"
          
          # Add library paths for linking
          export LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
            pkgs.alsa-lib
            pkgs.portaudio
            pkgs.libpulseaudio
          ]}:$LIBRARY_PATH"
          
          # Make sure gcc, pkg-config, and ffmpeg are available
          export PATH="${pkgs.gcc}/bin:${pkgs.pkg-config}/bin:${pkgs.ffmpeg}/bin${
            lib.optionalString (whisperPackage != null) ":${whisperPackage}/bin"
          }:$PATH"
          
          exec ${pkgs.uv}/bin/uvx voice-mode "$@"
        '';

        voice-mode = mkVoiceMode { };
        voice-mode-cuda = mkVoiceMode { whisperPackage = whisper-cpp-cuda; };
      in
      {
        packages = {
          default = voice-mode;
          inherit voice-mode whisper-cpp;
        } // lib.optionalAttrs isLinuxX86 {
          inherit whisper-cpp-cuda voice-mode-cuda;
        };
        
        devShells.default = pkgs.mkShell {
          # Build-time dependencies (available during build)
          nativeBuildInputs = with pkgs; [
            pkg-config
            gcc
            cmake
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            alsa-lib.dev  # ALSA headers for building simpleaudio
            libpulseaudio.dev # PulseAudio headers
          ];
          
          # Runtime dependencies
          buildInputs = with pkgs; [
            # Python
            pythonEnv
            uv
            
            # Audio libraries (runtime)
            portaudio
            libpulseaudio
            alsa-lib
            ffmpeg
            
            # Audio tools
            pulseaudio
            alsa-utils
            
            # Additional tools
            git
          ];
          
          shellHook = ''
            echo "Voice Mode NixOS development environment"
            echo "Python ${pkgs.python312.version} with uv and audio dependencies"
            
            # Set up library paths
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
              pkgs.portaudio
              pkgs.libpulseaudio
              pkgs.alsa-lib
              pkgs.stdenv.cc.cc.lib
            ]}:$LD_LIBRARY_PATH"
            
            # Set up pkg-config for build-time compilation
            export PKG_CONFIG_PATH="${pkgs.alsa-lib.dev}/lib/pkgconfig:${pkgs.portaudio}/lib/pkgconfig:${pkgs.libpulseaudio.dev}/lib/pkgconfig:$PKG_CONFIG_PATH"
            
            # Add development headers to C include path
            export CPATH="${pkgs.alsa-lib.dev}/include:${pkgs.portaudio}/include:${pkgs.libpulseaudio.dev}/include:$CPATH"
            
            # Add library paths for linking
            export LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
              pkgs.alsa-lib
              pkgs.portaudio
              pkgs.libpulseaudio
            ]}:$LIBRARY_PATH"
            
            # Create venv if it doesn't exist
            if [ ! -d .venv ]; then
              echo "Creating virtual environment..."
              uv venv
            fi
            
            echo ""
            echo "To activate the virtual environment, run: source .venv/bin/activate"
            echo "Then install voice-mode with: uv pip install -e ."
            echo "Or run directly with: uvx voice-mode"
          '';
        };
      });
}
