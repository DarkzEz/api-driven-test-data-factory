"""Read and validate JSON scenario files"""

import json
from pathlib import Path

from pydantic import ValidationError

from testdata_factory.errors import ConfigurationError
from testdata_factory.models import FactoryConfig


def load_config(path: str | Path) -> FactoryConfig:
    """Load a scenario file and convert user-facing failures into concise errors."""
    config_path = Path(path)
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Cannot read configuration file '{config_path}': {exc.strerror}"
        raise ConfigurationError(message) from exc

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid JSON in '{config_path}' at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    try:
        return FactoryConfig.model_validate(raw_data)
    except ValidationError as exc:
        issues = []
        for issue in exc.errors(include_url=False):
            location = ".".join(str(part) for part in issue["loc"])
            issues.append(f"- {location}: {issue['msg']}")
        raise ConfigurationError(
            f"Configuration '{config_path}' failed validation:\n" + "\n".join(issues)
        ) from exc
