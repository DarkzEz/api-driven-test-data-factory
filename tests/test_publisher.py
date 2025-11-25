import json

import httpx
import pytest
from pydantic import ValidationError

from testdata_factory.config import load_config
from testdata_factory.errors import ConfigurationError, PublishError
from testdata_factory.generator import TestDataGenerator
from testdata_factory.models import PublishReceipt
from testdata_factory.publisher import ApiPublisher


def _batch(example_config_path):
    return TestDataGenerator().generate(load_config(example_config_path))


def test_publish_sends_auth_idempotency_and_json(example_config_path):
    batch = _batch(example_config_path)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "status": "accepted",
                "batch_id": batch.batch_id,
                "accepted_count": len(batch.items),
                "duplicate": False,
            },
        )

    publisher = ApiPublisher("http://localhost:8080", transport=httpx.MockTransport(handler))
    receipt = publisher.publish(batch, token="test-token")

    assert receipt.status == "accepted"
    assert captured["headers"]["authorization"] == "Bearer test-token"
    assert captured["headers"]["idempotency-key"] == batch.batch_id
    assert captured["payload"]["batch_id"] == batch.batch_id
    assert len(captured["payload"]["items"]) == len(batch.items)


def test_publish_rejects_non_success_response(example_config_path):
    batch = _batch(example_config_path)
    publisher = ApiPublisher(
        "http://localhost:8080",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable")),
    )

    with pytest.raises(PublishError, match="HTTP 503"):
        publisher.publish(batch)


def test_publish_rejects_mismatched_receipt(example_config_path):
    batch = _batch(example_config_path)
    publisher = ApiPublisher(
        "http://localhost:8080",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                201,
                json={
                    "status": "accepted",
                    "batch_id": "0" * 64,
                    "accepted_count": len(batch.items),
                    "duplicate": False,
                },
            )
        ),
    )

    with pytest.raises(PublishError, match="does not match"):
        publisher.publish(batch)


def test_publish_rejects_wrong_accepted_count(example_config_path):
    batch = _batch(example_config_path)
    publisher = ApiPublisher(
        "http://localhost:8080",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                201,
                json={
                    "status": "accepted",
                    "batch_id": batch.batch_id,
                    "accepted_count": len(batch.items) - 1,
                    "duplicate": False,
                },
            )
        ),
    )

    with pytest.raises(PublishError, match="accepted_count"):
        publisher.publish(batch)


def test_http_is_rejected_for_non_loopback_without_explicit_opt_in():
    with pytest.raises(ConfigurationError, match="Cleartext HTTP"):
        ApiPublisher("http://example.internal")


def test_https_is_accepted_for_non_loopback():
    publisher = ApiPublisher("https://api.example.com")
    assert publisher.url == "https://api.example.com/api/v1/test-data"


def test_receipt_model_rejects_unknown_status():
    with pytest.raises(ValidationError):
        PublishReceipt.model_validate(
            {"status": "maybe", "batch_id": "a" * 64, "accepted_count": 3}
        )


def test_publish_reports_network_errors(example_config_path):
    batch = _batch(example_config_path)

    def fail_to_connect(request):
        raise httpx.ConnectError("connection refused", request=request)

    publisher = ApiPublisher(
        "http://localhost:8080",
        transport=httpx.MockTransport(fail_to_connect),
    )
    with pytest.raises(PublishError, match=r"API request failed \(ConnectError\)"):
        publisher.publish(batch)


def test_publish_rejects_invalid_json_receipt(example_config_path):
    batch = _batch(example_config_path)
    publisher = ApiPublisher(
        "http://localhost:8080",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json")),
    )

    with pytest.raises(PublishError, match="invalid publication receipt"):
        publisher.publish(batch)


def test_rejects_invalid_url_endpoint_and_timeout():
    with pytest.raises(ConfigurationError, match="absolute http:// or https://"):
        ApiPublisher("api.example.com")
    with pytest.raises(ConfigurationError, match="credentials, query, or fragment"):
        ApiPublisher("https://user:password@api.example.com")
    with pytest.raises(ConfigurationError, match="absolute path"):
        ApiPublisher("https://api.example.com", endpoint="api/v1/test-data")
    with pytest.raises(ConfigurationError, match="query string"):
        ApiPublisher("https://api.example.com", endpoint="/api/v1/test-data?debug=true")
    with pytest.raises(ConfigurationError, match="Timeout must be"):
        ApiPublisher("https://api.example.com", timeout_seconds=0)


def test_explicit_opt_in_allows_http_on_isolated_non_loopback_network():
    publisher = ApiPublisher("http://demo-api:8080", allow_insecure_http=True)
    assert publisher.url == "http://demo-api:8080/api/v1/test-data"


def test_malformed_port_is_rejected_as_configuration_error():
    with pytest.raises(ConfigurationError, match="malformed"):
        ApiPublisher("http://localhost:not-a-port")
    with pytest.raises(ConfigurationError, match="port must be"):
        ApiPublisher("http://localhost:0")


def test_publisher_and_demo_api_work_together_end_to_end(example_config_path):
    from fastapi.testclient import TestClient

    from testdata_factory.demo_api import InMemoryBatchStore, app

    app.state.batch_store = InMemoryBatchStore()
    receiver = TestClient(app)

    def forward_to_demo_api(request: httpx.Request) -> httpx.Response:
        response = receiver.post(
            str(request.url.path),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            response.status_code,
            headers={"content-type": "application/json"},
            content=response.content,
        )

    batch = _batch(example_config_path)
    publisher = ApiPublisher(
        "http://localhost:8080",
        transport=httpx.MockTransport(forward_to_demo_api),
    )

    first_receipt = publisher.publish(batch)
    second_receipt = publisher.publish(batch)

    assert first_receipt.duplicate is False
    assert second_receipt.duplicate is True
    assert first_receipt.batch_id == second_receipt.batch_id == batch.batch_id


def test_receipt_rejects_count_above_batch_limit():
    with pytest.raises(ValidationError, match="cannot exceed"):
        PublishReceipt.model_validate(
            {"status": "accepted", "batch_id": "a" * 64, "accepted_count": 501}
        )
