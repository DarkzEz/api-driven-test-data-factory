import json

import pytest
from pydantic import ValidationError

from testdata_factory.config import load_config
from testdata_factory.generator import TestDataGenerator
from testdata_factory.models import DataBatch


def test_generation_is_deterministic_for_same_config(example_config_path):
    config = load_config(example_config_path)

    first = TestDataGenerator().generate(config)
    second = TestDataGenerator().generate(config)

    assert first.to_payload() == second.to_payload()
    assert first.batch_id == second.batch_id


def test_generates_expected_count_unique_ids_and_metadata(example_config_path):
    config = load_config(example_config_path)
    batch = TestDataGenerator().generate(config)

    assert len(batch.items) == config.generation.count
    assert len({item.external_id for item in batch.items}) == len(batch.items)
    assert [item.metadata.sequence for item in batch.items] == list(range(1, 6))
    assert all(item.metadata.scenario == config.scenario for item in batch.items)
    assert all(item.metadata.seed == config.generation.seed for item in batch.items)


def test_payload_contains_content_derived_batch_id(example_config_path):
    batch = TestDataGenerator().generate(load_config(example_config_path))
    payload = batch.to_payload()

    assert payload["batch_id"] == batch.batch_id
    assert len(batch.batch_id) == 64
    assert payload["items"][0]["style"]["color"].startswith("#")


def test_seed_is_included_in_batch_identity(example_config_path, tmp_path):
    raw = json.loads(example_config_path.read_text(encoding="utf-8"))
    first_config_path = tmp_path / "first.json"
    second_config_path = tmp_path / "second.json"
    first_config_path.write_text(json.dumps(raw), encoding="utf-8")
    raw["generation"]["seed"] += 1
    second_config_path.write_text(json.dumps(raw), encoding="utf-8")

    first = TestDataGenerator().generate(load_config(first_config_path))
    second = TestDataGenerator().generate(load_config(second_config_path))
    assert first.batch_id != second.batch_id
    assert first.items[0].external_id != second.items[0].external_id


def test_template_change_changes_generated_external_ids(example_config_path, tmp_path):
    raw = json.loads(example_config_path.read_text(encoding="utf-8"))
    first_config_path = tmp_path / "first.json"
    second_config_path = tmp_path / "second.json"
    first_config_path.write_text(json.dumps(raw), encoding="utf-8")
    raw["template"]["titles"][0] += " revised"
    second_config_path.write_text(json.dumps(raw), encoding="utf-8")

    first = TestDataGenerator().generate(load_config(first_config_path))
    second = TestDataGenerator().generate(load_config(second_config_path))
    assert first.items[0].external_id != second.items[0].external_id


def test_batch_rejects_duplicate_external_ids(example_config_path):
    batch = TestDataGenerator().generate(load_config(example_config_path))
    duplicate = batch.items[1].model_copy(update={"external_id": batch.items[0].external_id})

    with pytest.raises(ValidationError, match="external_id values must be unique"):
        DataBatch(scenario=batch.scenario, seed=batch.seed, items=[batch.items[0], duplicate])


def test_batch_rejects_item_metadata_that_does_not_match_batch(example_config_path):
    batch = TestDataGenerator().generate(load_config(example_config_path))
    inconsistent = batch.items[0].model_copy(
        update={"metadata": batch.items[0].metadata.model_copy(update={"seed": batch.seed + 1})}
    )

    with pytest.raises(ValidationError, match="metadata.seed must match"):
        DataBatch(scenario=batch.scenario, seed=batch.seed, items=[inconsistent])


def test_batch_rejects_noncontiguous_sequence(example_config_path):
    batch = TestDataGenerator().generate(load_config(example_config_path))
    noncontiguous = batch.items[1].model_copy(
        update={"metadata": batch.items[1].metadata.model_copy(update={"sequence": 9})}
    )

    with pytest.raises(ValidationError, match="contiguous and start at 1"):
        DataBatch(
            scenario=batch.scenario,
            seed=batch.seed,
            items=[batch.items[0], noncontiguous],
        )
