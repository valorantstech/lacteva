"""Background worker registry (OBS-001).

The relay dispatcher and consumer runner are the loops that actually move
work through the platform. When one of them dies, every synchronous surface
keeps answering perfectly while nothing downstream happens — collections are
recorded, and no notification is sent, no receipt generated, no projection
updated. That is the most dangerous failure shape a platform of this design
has, because it looks healthy.

This registry exists so a health probe can answer "is the loop alive?"
without guessing from side effects. It records the asyncio task, so a task
that raised and died reports stopped rather than merely idle.
"""

import asyncio

import structlog

log = structlog.get_logger("workers")

_workers: dict[str, asyncio.Task] = {}


def register(name: str, task: asyncio.Task) -> None:
    _workers[name] = task
    log.info("worker_registered", worker=name)


def unregister(name: str) -> None:
    _workers.pop(name, None)


def clear() -> None:
    _workers.clear()


def status() -> dict[str, bool]:
    """Name → alive. A task that finished (normally or by exception) is dead:
    these loops are meant to run for the process's lifetime."""
    return {name: not task.done() for name, task in _workers.items()}


def failures() -> dict[str, str]:
    """Name → exception type, for workers that died of an exception. Used by
    the runbook to distinguish 'cancelled during shutdown' from 'crashed'."""
    result: dict[str, str] = {}
    for name, task in _workers.items():
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None:
                result[name] = type(exc).__name__
    return result
