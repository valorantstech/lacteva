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
    # Reset the shutdown flag too: a process (or a test) that starts workers
    # after a shutdown must not inherit a set flag and stop immediately.
    _stop.clear()


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


# --- Graceful shutdown (DEP-001) -------------------------------------------
#
# `task.cancel()` throws CancelledError wherever the loop happens to be — which
# may be inside a consumer's transaction, between the handler's write and the
# ledger row that records it. The framework is built so a crash there is safe
# (the transaction rolls back and the event is retried), but "safe" is not the
# same as "clean": every SIGTERM would leave in-flight work to be redone, and a
# rolling deploy is a lot of SIGTERMs.
#
# So shutdown is COOPERATIVE. The loops finish the unit of work they are in,
# commit it, and then notice the flag at their next sleep. Cancellation remains
# as the backstop for a loop that overruns its grace period, because a
# shutdown that can hang is not a shutdown.

_stop = asyncio.Event()

# How long a worker gets to finish its current unit of work. Longer than one
# poll interval by a wide margin, shorter than any orchestrator's kill timeout.
DEFAULT_GRACE_SECONDS = 20.0


def request_stop() -> None:
    """Ask every loop to stop after its current unit of work."""
    _stop.set()


def stopping() -> bool:
    return _stop.is_set()


async def sleep(seconds: float) -> None:
    """Sleep between iterations, but wake at once when shutdown is requested.

    This is the whole mechanism: a loop that sleeps here is interruptible
    between units of work and uninterruptible during one.
    """
    try:
        await asyncio.wait_for(_stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def shutdown(grace_seconds: float = DEFAULT_GRACE_SECONDS) -> dict[str, str]:
    """Stop every registered worker. Returns name → how it ended.

    Reports rather than assumes: an operator reading the shutdown log should
    be able to tell a clean drain from a forced one, because the difference
    predicts whether the next start has work to redo.
    """
    request_stop()
    if not _workers:
        return {}
    outcome: dict[str, str] = {}
    pending = {name: task for name, task in _workers.items() if not task.done()}
    if pending:
        _, overran = await asyncio.wait(pending.values(), timeout=grace_seconds)
        for name, task in pending.items():
            if task in overran:
                task.cancel()
                outcome[name] = "cancelled_after_grace"
            else:
                outcome[name] = "drained"
    for name in _workers:
        outcome.setdefault(name, "already_stopped")
    if overrun := [n for n, how in outcome.items() if how == "cancelled_after_grace"]:
        # Let the cancellation actually land before the caller moves on.
        # `cancel()` only requests it; the task still has to unwind, and
        # disposing the database engine underneath a task that is still
        # closing its session turns a forced shutdown into a stack trace on
        # the way out — which is the last thing an operator needs to read.
        await asyncio.gather(*(_workers[name] for name in overrun), return_exceptions=True)
        log.warning("workers_forced", workers=overrun, grace_seconds=grace_seconds)
    else:
        log.info("workers_drained", workers=sorted(outcome))
    return outcome
