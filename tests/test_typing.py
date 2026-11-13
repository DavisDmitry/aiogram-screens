"""Static typing of generic screens.

assert_type() is a no-op at runtime; mypy (run by `nox -s lint`) checks that
each expression has exactly the stated type.
"""

from typing import Any, assert_type

from aiogram.methods import EditMessageText, SendMessage, SendRichMessage
from aiogram.types import InputRichMessage

from aiogram_screens import EditableTextMessageScreen, Replacer, TextMessageScreen


class Text(EditableTextMessageScreen[str]):
    def create_text(self) -> str:
        return "text"


class Rich(EditableTextMessageScreen[InputRichMessage]):
    def create_text(self) -> InputRichMessage:
        return InputRichMessage(html="<b>rich</b>")


class Mismatch(TextMessageScreen[str]):
    # Type checkers must reject a rich text in a str screen. If mypy stops
    # reporting it, warn_unused_ignores fails the lint session.
    def create_text(self) -> InputRichMessage:  # type: ignore[override]
        return InputRichMessage(html="x")


def test_send_type_follows_text_type() -> None:
    assert_type(Text().send(1), SendMessage)
    assert_type(Rich().send(1), SendRichMessage)
    assert isinstance(Text().send(1), SendMessage)
    assert isinstance(Rich().send(1), SendRichMessage)


def test_edit_type() -> None:
    assert_type(Text().edit(chat_id=1, message_id=2), EditMessageText)
    assert_type(Rich().edit(chat_id=1, message_id=2), EditMessageText)


async def _replacer_types(message: Any) -> None:
    text, rich = Replacer(Text()), Replacer(Rich())
    assert_type(text, Replacer[Text])
    assert_type(await text.replace(message), SendMessage)
    assert_type(await rich.replace(message), SendRichMessage)
    assert_type(await text.new(message), SendMessage)
    assert_type(await rich.new(message), SendRichMessage)
    assert_type(await text.edit_or_replace(message), SendMessage | EditMessageText)
    assert_type(await rich.edit_or_replace(message), SendRichMessage | EditMessageText)


def test_replacer_types_are_checked_statically() -> None:
    # The checks above only need mypy; running them would require a bot.
    assert callable(_replacer_types)
