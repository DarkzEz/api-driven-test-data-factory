"""Command line entry point"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from testdata_factory import __version__
from testdata_factory.config import load_config
from testdata_factory.errors import ConfigurationError, FactoryError
from testdata_factory.generator import TestDataGenerator
from testdata_factory.publisher import ApiPublisher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testdata-factory",
        description="Generate deterministic test fixtures and optionally publish them to an API.",
        epilog=(
            "Publication is opt-in: without --execute, the command only generates and prints "
            "the payload. Set TESTDATA_API_TOKEN for bearer authentication."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", required=True, help="Path to a JSON scenario file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print payload without network calls (default)",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Send the generated batch to the configured API",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("TESTDATA_API_URL"),
        help="API base URL (or set TESTDATA_API_URL)",
    )
    parser.add_argument(
        "--endpoint",
        default="/api/v1/test-data",
        help="API path (default: /api/v1/test-data)",
    )
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help=(
            "Allow cleartext HTTP for an isolated non-loopback network, "
            "such as a local Compose network"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to save the generated request payload as JSON",
    )
    return parser


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        batch = TestDataGenerator().generate(config)
        payload = batch.to_payload()

        if args.output:
            try:
                args.output.write_text(_json_text(payload), encoding="utf-8")
            except OSError as exc:
                raise ConfigurationError(
                    f"Cannot write output file '{args.output}': {exc.strerror}"
                ) from exc

        if not args.execute:
            print(_json_text(payload), end="")
            return 0

        if not args.base_url:
            raise ConfigurationError(
                "--execute requires --base-url or the TESTDATA_API_URL environment variable"
            )

        token = os.getenv("TESTDATA_API_TOKEN")
        publisher = ApiPublisher(
            args.base_url,
            endpoint=args.endpoint,
            allow_insecure_http=args.allow_insecure_http,
        )
        receipt = publisher.publish(batch, token=token)
        print(_json_text(receipt.model_dump(mode="json")), end="")
        return 0
    except FactoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
