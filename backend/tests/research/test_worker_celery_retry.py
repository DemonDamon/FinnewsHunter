"""Celery acks_late redelivery semantics for research worker failures."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from app.research.errors import DomainError
from app.research.worker import (
    _execute_task_async,
    should_re_raise_for_celery,
)


def test_persistence_failed_is_retryable_for_celery() -> None:
    err = DomainError(
        code="persistence_failed",
        safe_message="run claim failed",
        retryable=True,
    )
    assert should_re_raise_for_celery(err) is True


def test_non_retryable_domain_error_is_acked() -> None:
    err = DomainError(
        code="execution_fenced",
        safe_message="research execution is fenced",
        retryable=False,
    )
    assert should_re_raise_for_celery(err) is False


def test_execute_task_async_propagates_retryable_persistence_failed() -> None:
    class _RetryLedger:
        async def claim_run(self, **kwargs):
            raise DomainError(
                code="persistence_failed",
                safe_message="run claim failed",
                retryable=True,
            )

    class _Registry:
        async def record_heartbeat(self, **kwargs):
            return None

    with pytest.raises(DomainError) as error:
        asyncio.run(
            _execute_task_async(
                run_id=str(uuid4()),
                dispatch_id="dispatch-retry",
                contract_version="research-v1.1",
                ledger=_RetryLedger(),
                registry=_Registry(),
                worker_id="research.worker.test",
            )
        )
    assert error.value.code == "persistence_failed"
    assert should_re_raise_for_celery(error.value) is True


def test_celery_task_handler_re_raises_retryable_domain_error() -> None:
    from app.research.worker import make_celery_task

    class _App:
        def task(self, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    task = make_celery_task(_App())

    async def _boom(**kwargs):
        raise DomainError(
            code="persistence_failed",
            safe_message="run claim failed",
            retryable=True,
        )

    import app.research.worker as worker_module

    original = worker_module._execute_task_async
    worker_module._execute_task_async = _boom
    worker_module._worker_stack["main"] = {
        "ledger": object(),
        "executor_registry": object(),
        "allow_fixture": True,
    }
    try:
        with pytest.raises(DomainError):
            task(None, str(uuid4()), "d1", "research-v1.1")
    finally:
        worker_module._execute_task_async = original
        worker_module._worker_stack.clear()
