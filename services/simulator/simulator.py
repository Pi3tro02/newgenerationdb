"""
Entry point del simulatore real-time.
"""

import importlib.util
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_PATH = (
    WORKSPACE_ROOT
    / "services"
    / "voltdb-engine"
    / "app"
    / "simulator.py"
)

def load_simulator_module():
    """
    Metodo che carica il modello del simulatore.
    """
    spec = importlib.util.spec_from_file_location(
        "realtime_simulator",
        SIMULATOR_PATH,
    )

    if spec is None or spec.loader is None:
        raise ImportError(f"Impossibile caricare il simulatore: {SIMULATOR_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module

def main() -> int:
    simulator = load_simulator_module()
    return simulator.main()

if __name__ == "__main__":
    raise SystemExit(main())
