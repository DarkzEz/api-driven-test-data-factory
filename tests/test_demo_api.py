from fastapi.testclient import TestClient

from testdata_factory.config import load_config
from testdata_factory.demo_api import InMemoryBatchStore, app
from testdata_factory.generator import TestDataGenerator


def test_demo_api_accepts_and_deduplicates_same_batch(example_config_path):
    app.state.batch_store = InMemoryBatchStore()
    client = TestClient(app)
    batch = TestDataGenerator().generate(load_config(example_config_path))
    payload = batch.to_payload()
    headers = {"Idempotency-Key": batch.batch_id}

    first = client.post("/api/v1/test-data", json=payload, headers=headers)
    second = client.post("/api/v1/test-data", json=payload, headers=headers)

    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["accepted_count"] == len(batch.items)


def test_demo_api_rejects_wrong_idempotency_key(example_config_path):
    app.state.batch_store = InMemoryBatchStore()
    client = TestClient(app)
    batch = TestDataGenerator().generate(load_config(example_config_path))

    response = client.post(
        "/api/v1/test-data",
        json=batch.to_payload(),
        headers={"Idempotency-Key": "wrong-key"},
    )
    assert response.status_code == 400


def test_demo_api_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_api_can_read_stored_batch_and_returns_404_for_unknown_id(example_config_path):
    app.state.batch_store = InMemoryBatchStore()
    client = TestClient(app)
    batch = TestDataGenerator().generate(load_config(example_config_path))
    client.post(
        "/api/v1/test-data",
        json=batch.to_payload(),
        headers={"Idempotency-Key": batch.batch_id},
    )

    found = client.get(f"/api/v1/test-data/{batch.batch_id}")
    missing = client.get(f"/api/v1/test-data/{'0' * 64}")

    assert found.status_code == 200
    assert found.json()["batch_id"] == batch.batch_id
    assert missing.status_code == 404


def test_demo_api_rejects_content_hash_mismatch(example_config_path):
    app.state.batch_store = InMemoryBatchStore()
    client = TestClient(app)
    batch = TestDataGenerator().generate(load_config(example_config_path))
    payload = batch.to_payload()
    payload["batch_id"] = "0" * 64

    response = client.post(
        "/api/v1/test-data",
        json=payload,
        headers={"Idempotency-Key": payload["batch_id"]},
    )
    assert response.status_code == 422


def test_demo_api_rejects_mismatched_item_metadata(example_config_path):
    app.state.batch_store = InMemoryBatchStore()
    client = TestClient(app)
    batch = TestDataGenerator().generate(load_config(example_config_path))
    payload = batch.to_payload()
    payload["items"][0]["metadata"]["scenario"] = "different-scenario"
    payload["batch_id"] = batch.batch_id

    response = client.post(
        "/api/v1/test-data",
        json=payload,
        headers={"Idempotency-Key": payload["batch_id"]},
    )
    assert response.status_code == 422
