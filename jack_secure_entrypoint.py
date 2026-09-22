from __future__ import annotations

import sys
from pathlib import Path

import jack_kernel as jk


def main() -> None:
    jk._install_bundled_runtime_extensions()

    # The interactive launcher spawns a fresh serving child. Keep both the
    # Responses API compatibility route and the evidence-provenance guard active
    # in that child rather than falling back to bare jack_kernel.py.
    jk._server_command = lambda: [
        sys.executable,
        str(Path(__file__).resolve()),
        "--serve",
    ]
    jk.main()


if __name__ == "__main__":
    main()
