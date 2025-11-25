import json

from testdata_factory.cli import main
from testdata_factory.models import PublishReceipt


def test_dry_run_outputs_batch_and_does_not_publish(example_config_path, capsys, monkeypatch):
    from testdata_factory.publisher import ApiPublisher

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not make an API call")

    monkeypatch.setattr(ApiPublisher, "publish", fail_if_called)
    code = main(["--config", str(example_config_path), "--dry-run"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert len(payload["items"]) == 5
    assert len(payload["batch_id"]) == 64
    assert captured.err == ""


def test_execute_requires_api_base_url(example_config_path, capsys, monkeypatch):
    monkeypatch.delenv("TESTDATA_API_URL", raising=False)
    code = main(["--config", str(example_config_path), "--execute"])
    captured = capsys.readouterr()

    assert code == 2
    assert "requires --base-url" in captured.err


def test_execute_prints_validated_receipt(example_config_path, capsys, monkeypatch):
    from testdata_factory.publisher import ApiPublisher

    receipt = PublishReceipt(
        status="accepted",
        batch_id="a" * 64,
        accepted_count=5,
        duplicate=False,
    )

    def fake_publish(self, batch, *, token=None):
        return receipt

    monkeypatch.setattr(ApiPublisher, "publish", fake_publish)
    code = main(
        [
            "--config",
            str(example_config_path),
            "--execute",
            "--base-url",
            "https://api.example.com",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert json.loads(captured.out)["status"] == "accepted"


def test_dry_run_can_write_payload_to_file(example_config_path, tmp_path, capsys):
    output = tmp_path / "generated.json"
    code = main(["--config", str(example_config_path), "--output", str(output)])
    capsys.readouterr()

    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["items"]


def test_output_write_failure_is_reported(example_config_path, tmp_path, capsys):
    output = tmp_path / "missing" / "batch.json"
    code = main(["--config", str(example_config_path), "--output", str(output)])
    captured = capsys.readouterr()

    assert code == 2
    assert "Cannot write output file" in captured.err
