import json

import pytest

from testdata_factory.config import load_config
from testdata_factory.errors import ConfigurationError


def test_loads_example_configuration(example_config_path):
    config = load_config(example_config_path)

    assert config.scenario == "homepage-content-fixtures"
    assert config.generation.count == 5
    assert len(config.template.styles) == 3


def test_rejects_unknown_configuration_fields(tmp_path, example_config_path):
    data = json.loads(example_config_path.read_text(encoding="utf-8"))
    data["generation"]["unreviewed_option"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unreviewed_option"):
        load_config(path)


def test_invalid_json_has_location_in_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"scenario": ', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="line 1, column"):
        load_config(path)


def test_missing_configuration_is_a_clear_error(tmp_path):
    with pytest.raises(ConfigurationError, match="Cannot read configuration"):
        load_config(tmp_path / "missing.json")
