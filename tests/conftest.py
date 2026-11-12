from datetime import datetime
from typing import Any

import pytest
from aiogram.types import Chat, Message


@pytest.fixture
def chat() -> Chat:
    return Chat(id=100, type="supergroup")


@pytest.fixture
def make_message(chat: Chat) -> Any:
    def factory(**kwargs: Any) -> Message:
        return Message(
            **{
                "message_id": 42,
                "date": datetime(2026, 1, 1),
                "chat": chat,
                "text": "old",
                **kwargs,
            }
        )

    return factory
