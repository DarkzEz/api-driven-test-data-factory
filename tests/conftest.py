from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = ROOT / "examples" / "content-batch.json"


@pytest.fixture

def example_config_path() -> Path:
    return EXAMPLE_CONFIG
