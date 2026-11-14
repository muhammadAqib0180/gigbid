from __future__ import annotations

from fastapi import Request

from apps.api.dispatch import Dispatcher
from worker.runner import GraphRunner


def runner(request: Request) -> GraphRunner:
    return request.app.state.runner


def dispatcher(request: Request) -> Dispatcher:
    return request.app.state.dispatcher


def iso(d) -> str | None:
    return d.isoformat() if d else None
