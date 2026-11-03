"""Langfuse traces of the AI actions: what each model call was given, returned and cost.

One trace per user action (generate-draft, check-sources, suggest-topics), named after it,
with a generation for every model call inside. Off unless LANGFUSE_PUBLIC_KEY and
LANGFUSE_SECRET_KEY are set. Spans are sent from a background thread, and tracing never fails
a request: a client that can't be built leaves tracing off, and a failed update is logged and
dropped. Inputs are always set explicitly, so provider keys and headers never reach a trace.
"""

import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from functools import lru_cache
from typing import Any

from langfuse import Langfuse, ObservationTypeLiteral, propagate_attributes

from app.config import get_settings
from app.local_scope import LOCAL_USER_ID

logger = logging.getLogger(__name__)


@lru_cache
def tracer() -> Langfuse | None:
    """None when the client can't be built, e.g. a malformed LANGFUSE_* environment value."""
    settings = get_settings()
    public_key = settings.langfuse_public_key.strip()
    secret_key = settings.langfuse_secret_key.get_secret_value().strip()
    try:
        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=settings.langfuse_base_url,
            environment=settings.environment,
            tracing_enabled=bool(public_key and secret_key),
        )
    except Exception as exc:
        # The type only: a message could quote a configured value.
        logger.warning("tracing_off error=%s", type(exc).__name__)
        return None


class Observation:
    """An observation whose updates can't fail the work they describe."""

    def __init__(self, observation: Any = None):
        self.observation = observation

    def update(self, **attributes: Any) -> None:
        if self.observation is None:
            return
        try:
            self.observation.update(**attributes)
        except Exception as exc:
            logger.warning("tracing_update_dropped error=%s", type(exc).__name__)


@contextmanager
def observed(name: str, as_type: ObservationTypeLiteral, attributes: dict) -> Iterator[Observation]:
    with ExitStack() as stack:
        observation = Observation()
        client = tracer()
        if client is not None:
            # The SDK overloads on each literal type; the attributes a type accepts are the
            # caller's.
            start: Any = client.start_as_current_observation
            try:
                observation = Observation(
                    stack.enter_context(start(name=name, as_type=as_type, **attributes))
                )
            except Exception as exc:
                logger.warning("tracing_start_dropped error=%s", type(exc).__name__)
        yield observation


@contextmanager
def action(name: str, *, input: Any, session_id: str | None = None) -> Iterator[Observation]:
    """The root of one trace. session_id groups a draft with its later source checks."""
    with observed(name, "span", {"input": input}) as root:
        with ExitStack() as stack:
            if root.observation is not None:
                try:
                    stack.enter_context(
                        propagate_attributes(user_id=str(LOCAL_USER_ID), session_id=session_id)
                    )
                except Exception as exc:
                    logger.warning("tracing_attributes_dropped error=%s", type(exc).__name__)
            yield root


def step(name: str, *, as_type: ObservationTypeLiteral = "span", **attributes: Any):
    """An observation nested under the active one, such as embed-topic or retrieve-sources."""
    return observed(name, as_type, attributes)


def source_list(sources: list[dict]) -> list[dict]:
    """What a retrieval returned, without the chunk text the writer's input already shows."""
    return [
        {
            "chunk_id": source.get("chunk_id"),
            "document_id": source.get("document_id"),
            "title": source.get("title"),
            "kind": source.get("kind"),
            "distance": source.get("distance"),
        }
        for source in sources
    ]
