from __future__ import annotations

import sys
from pathlib import Path

import jack_kernel as jk


def main() -> None:
    # All bundled predecessor authority/security extensions converge through
    # this shared Kernel installer before Phase 8 establishes source authority.
    jk._install_bundled_runtime_extensions()

    # The interactive launcher process is not itself the serving Kernel. Seal
    # Phase-8 source authority only in the --serve process, after predecessor
    # extensions are installed and before Jack enters the serving lifecycle.
    if "--serve" in sys.argv[1:]:
        import jack_source_drift_guard

        jack_source_drift_guard.install(
            jk,
            launch_entrypoint_path=Path(__file__).resolve(),
        )

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
