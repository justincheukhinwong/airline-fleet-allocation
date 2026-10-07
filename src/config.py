"""Project paths and expected source files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw"
RESULT_DIR = ROOT / "results"
FIGURE_DIR = ROOT / "figures"
INPUTS = {f"T100_{year}": DATA_DIR / f"T100_{year}.zip" for year in (2019, 2023, 2024, 2025)}
INPUTS.update(
    aircraft_lookup=ROOT / "data" / "reference" / "L_AIRCRAFT_TYPE.csv",
    taiwan_annual=DATA_DIR / "108_112-114.zip",
)

def validate_inputs(inputs=INPUTS):
    missing = [str(p.relative_to(ROOT)) for p in inputs.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing inputs: " + ", ".join(missing) + ". See data/README.md.")
