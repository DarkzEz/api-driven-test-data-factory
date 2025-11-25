"""Local demonstration receiver. It's intentionally not a prod persistence layer"""

from __future__ import annotations

from threading import Lock
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from testdata_factory.models import IncomingBatch, PublishReceipt

app = FastAPI(
    title="Test Data Factory Demo Receiver",
    version="1.0.0",
    description="Local API used to exercise the factory publication flow",
)


class InMemoryBatchStore:
    """Thread-safe, process-local store for repeatable local demos"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._batches: dict[str, dict[str, object]] = {}

    def accept(self, batch: IncomingBatch) -> tuple[PublishReceipt, bool]:
        with self._lock:
            existing = self._batches.get(batch.batch_id)
            if existing is not None:
                return (
                    PublishReceipt(
                        status="accepted",
                        batch_id=batch.batch_id,
                        accepted_count=len(batch.items),
                        duplicate=True,
                    ),
                    True,
                )
            self._batches[batch.batch_id] = batch.model_dump(mode="json")
            return (
                PublishReceipt(
                    status="accepted",
                    batch_id=batch.batch_id,
                    accepted_count=len(batch.items),
                    duplicate=False,
                ),
                False,
            )

    def get(self, batch_id: str) -> dict[str, object] | None:
        with self._lock:
            stored = self._batches.get(batch_id)
            return stored.copy() if stored is not None else None


app.state.batch_store = InMemoryBatchStore()


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/test-data",
    response_model=PublishReceipt,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": PublishReceipt}},
    tags=["test data"],
)
def receive_batch(
    batch: IncomingBatch,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    if not idempotency_key or idempotency_key != batch.batch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must match the content-derived batch_id",
        )

    receipt, duplicate = request.app.state.batch_store.accept(batch)
    response_status = status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED
    return JSONResponse(status_code=response_status, content=receipt.model_dump(mode="json"))


@app.get("/api/v1/test-data/{batch_id}", tags=["test data"])
def get_batch(batch_id: str, request: Request) -> dict[str, object]:
    stored = request.app.state.batch_store.get(batch_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return stored
