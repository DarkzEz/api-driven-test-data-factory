"""HTTP publication with explicit safety checks and response validation"""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from testdata_factory.errors import ConfigurationError, PublishError
from testdata_factory.models import DataBatch, PublishReceipt

_LOOPBACK_HOSTS = {"localhost"}


def _is_loopback_host(host: str) -> bool:
    if host.lower() in _LOOPBACK_HOSTS:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def validate_base_url(base_url: str, *, allow_insecure_http: bool = False) -> str:
    """Validate base URL before using it for a potentially mutating request"""
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        port = parsed.port
        httpx.URL(base_url)
    except (ValueError, httpx.InvalidURL) as exc:
        raise ConfigurationError("API base URL is malformed") from exc

    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ConfigurationError("API base URL must be an absolute http:// or https:// URL")
    if port == 0:
        raise ConfigurationError("API base URL port must be between 1 and 65535")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("API base URL must not contain credentials, query, or fragment")
    if parsed.scheme == "http" and not (_is_loopback_host(hostname) or allow_insecure_http):
        raise ConfigurationError(
            "Cleartext HTTP is allowed only for loopback targets; use HTTPS or explicitly "
            "pass --allow-insecure-http for an isolated local network"
        )
    return base_url.rstrip("/")


class ApiPublisher:
    """Publish complete batch to the factory JSON API contract"""

    def __init__(
        self,
        base_url: str,
        *,
        endpoint: str = "/api/v1/test-data",
        timeout_seconds: float = 5.0,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = validate_base_url(base_url, allow_insecure_http=allow_insecure_http)
        if not endpoint.startswith("/") or endpoint.startswith("//"):
            raise ConfigurationError(
                "API endpoint must be an absolute path such as /api/v1/test-data"
            )
        if "?" in endpoint or "#" in endpoint:
            raise ConfigurationError("API endpoint must not contain a query string or fragment")
        if not 0.1 <= timeout_seconds <= 60:
            raise ConfigurationError("Timeout must be between 0.1 and 60 seconds")
        self.url = f"{self.base_url}{endpoint}"
        self.timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 2.0))
        self.transport = transport

    def publish(self, batch: DataBatch, *, token: str | None = None) -> PublishReceipt:
        payload = batch.to_payload()
        batch_id = str(payload["batch_id"])
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": batch_id,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"API rejected the batch with HTTP {exc.response.status_code} "
                f"({exc.response.reason_phrase})"
            ) from exc
        except httpx.RequestError as exc:
            raise PublishError(
                f"API request failed ({type(exc).__name__}); "
                "check the URL, network, and service health"
            ) from exc

        try:
            receipt = PublishReceipt.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise PublishError("API returned an invalid publication receipt") from exc

        if receipt.batch_id != batch_id:
            raise PublishError("API receipt batch_id does not match the submitted batch")
        if receipt.accepted_count != len(batch.items):
            raise PublishError(
                "API receipt accepted_count does not match the submitted item count"
            )
        return receipt
