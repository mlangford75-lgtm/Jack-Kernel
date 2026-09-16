from __future__ import annotations

import sys
from pathlib import Path

import jack_evidence_guard
import jack_kernel as jk
import jack_responses_compat


def main() -> None:
    jack_evidence_guard.install(jk)
    jack_responses_compat.register(jk)
    jk._register_runtime_manifest_components({
        "jack_secure_entrypoint.py": Path(__file__).resolve(),
        "jack_evidence_guard.py": Path(jack_evidence_guard.__file__).resolve(),
        "jack_responses_compat.py": Path(jack_responses_compat.__file__).resolve(),
    })

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
