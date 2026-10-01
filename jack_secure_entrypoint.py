from __future__ import annotations

import sys
from pathlib import Path

import jack_kernel as jk


def main() -> None:
    # All bundled authority/security extensions, including the Phase-5
    # Consequence Gate, converge through this shared Kernel installer.
    jk._install_bundled_runtime_extensions()

    # The interactive launcher spawns a fresh serving child. Keep the bundled
    # runtime-extension path active in that child rather than falling back to a
    # different authority surface.
    jk._server_command = lambda: [
        sys.executable,
        str(Path(__file__).resolve()),
        "--serve",
    ]
    jk.main()


if __name__ == "__main__":
    main()
