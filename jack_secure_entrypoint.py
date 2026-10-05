from __future__ import annotations

import sys
from pathlib import Path

import jack_kernel as jk


def main() -> None:
    # All bundled predecessor authority/security extensions converge through
    # this shared Kernel installer before Phase 8 establishes source authority.
    jk._install_bundled_runtime_extensions()

    # Phase 8B seals the complete source-authority component set only after the
    # predecessor extensions have installed, but before Jack enters its serving
    # lifecycle. The secure entrypoint is included because this launch path
    # actually established the running Kernel.
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
