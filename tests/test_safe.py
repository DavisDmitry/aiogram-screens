import logging
from collections.abc import Generator
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage

from aiogram_screens import safe_call


class FakeMethod:
    """Awaitable stand-in for a bot-bound TelegramMethod."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def __await__(self) -> Generator[Any, None, Any]:
        if self.error is not None:
            raise self.error
        return self.result
        yield  # makes this a generator


def api_error() -> TelegramBadRequest:
    return TelegramBadRequest(
        method=DeleteMessage(chat_id=1, message_id=1),
        message="Bad Request: message to delete not found",
    )


async def test_success() -> None:
    assert await safe_call(FakeMethod(result="ok")) == (True, "ok")  # type: ignore[arg-type]


async def test_api_error_is_logged_as_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result: object = await safe_call(
            FakeMethod(error=api_error())  # type: ignore[arg-type]
        )
    assert result == (False, None)
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


async def test_non_api_error_is_raised_by_default() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        await safe_call(FakeMethod(error=RuntimeError("boom")))  # type: ignore[arg-type]


async def test_non_api_error_can_be_suppressed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result: object = await safe_call(
            FakeMethod(error=RuntimeError("boom")),  # type: ignore[arg-type]
            raise_non_api_error=False,
        )
    assert result == (False, None)
    assert [r.levelno for r in caplog.records] == [logging.ERROR]


async def test_custom_level_resolver(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        await safe_call(
            FakeMethod(error=api_error()),  # type: ignore[arg-type]
            log_level_resolver=lambda error: logging.INFO,
        )
    assert [(r.name, r.levelno) for r in caplog.records] == [
        ("aiogram_screens.safe", logging.INFO)
    ]


async def test_cancellation_is_not_swallowed() -> None:
    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await safe_call(FakeMethod(error=asyncio.CancelledError()))  # type: ignore[arg-type]
