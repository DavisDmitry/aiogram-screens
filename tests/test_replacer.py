from typing import Any

import pytest
from aiogram.methods import (
    DeleteMessage,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import (
    Chat,
    DirectMessagesTopic,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from aiogram_screens import (
    EditableMessageScreen,
    MessageScreen,
    NewReplyParameters,
    Replacer,
)

KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="ok")]]
)


class Plain(MessageScreen):
    def create_text(self) -> str:
        return "plain"


class Editable(EditableMessageScreen):
    def create_text(self) -> str:
        return "editable"

    def create_reply_markup(self) -> InlineKeyboardMarkup:
        return KEYBOARD


class FakeSafeCall:
    """Records called methods instead of sending them to Telegram."""

    def __init__(self) -> None:
        self.calls: list[TelegramMethod[Any]] = []
        self.failing: set[type] = set()

    async def __call__(
        self, method: TelegramMethod[Any], **kwargs: Any
    ) -> tuple[bool, Any]:
        self.calls.append(method)
        if type(method) in self.failing:
            return False, None
        return True, True

    @property
    def types(self) -> list[type]:
        return [type(call) for call in self.calls]


@pytest.fixture
def safe_call(monkeypatch: pytest.MonkeyPatch) -> FakeSafeCall:
    fake = FakeSafeCall()
    monkeypatch.setattr("aiogram_screens.replacer.safe_call", fake)
    return fake


@pytest.fixture
def inaccessible(chat: Chat) -> InaccessibleMessage:
    return InaccessibleMessage(chat=chat, message_id=42)


# --- replace ---


async def test_replace_deletes_message(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).replace(make_message())
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendMessage)
    assert (method.chat_id, method.text) == (100, "plain")


async def test_replace_falls_back_to_removing_markup(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    safe_call.failing.add(DeleteMessage)
    await Replacer(Plain()).replace(make_message())
    assert safe_call.types == [DeleteMessage, EditMessageReplyMarkup]


async def test_replace_copies_message_context(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    message = make_message(
        business_connection_id="biz",
        message_thread_id=7,
        direct_messages_topic=DirectMessagesTopic(topic_id=3),
    )
    method = await Replacer(Plain()).replace(message, parse_mode="HTML")
    assert isinstance(method, SendMessage)
    assert method.business_connection_id == "biz"
    assert method.message_thread_id == 7
    assert method.direct_messages_topic_id == 3
    assert method.parse_mode == "HTML"


async def test_replace_inaccessible_message(
    safe_call: FakeSafeCall, inaccessible: InaccessibleMessage
) -> None:
    method = await Replacer(Plain()).replace(inaccessible)
    assert safe_call.calls == []
    assert method.chat_id == 100
    assert method.business_connection_id is None
    assert method.message_thread_id is None


# --- edit_or_replace ---


async def test_edit_or_replace_edits_editable_screen(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Editable()).edit_or_replace(make_message())
    assert safe_call.calls == []
    assert isinstance(method, EditMessageText)
    assert (method.chat_id, method.message_id) == (100, 42)
    assert method.text == "editable"
    assert method.reply_markup == KEYBOARD


async def test_edit_or_replace_replaces_plain_screen(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).edit_or_replace(make_message())
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendMessage)


async def test_edit_or_replace_replaces_inaccessible_message(
    safe_call: FakeSafeCall, inaccessible: InaccessibleMessage
) -> None:
    method = await Replacer(Editable()).edit_or_replace(inaccessible)
    assert isinstance(method, SendMessage)
    assert method.text == "editable"


async def test_edit_or_replace_forwards_options_on_fallback(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).edit_or_replace(
        make_message(), parse_mode="HTML", link_preview_options=None
    )
    assert isinstance(method, SendMessage)
    assert method.parse_mode == "HTML"
    assert method.link_preview_options is None


# --- new ---


async def test_new_removes_old_markup(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).new(make_message(message_thread_id=7))
    assert safe_call.types == [EditMessageReplyMarkup]
    assert method.chat_id == 100
    assert method.message_thread_id == 7
    assert method.reply_parameters is None


async def test_new_replies_to_old_message(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).new(
        make_message(),
        reply_parameters=NewReplyParameters(allow_sending_without_reply=True),
    )
    assert method.reply_parameters is not None
    assert method.reply_parameters.message_id == 42
    assert method.reply_parameters.chat_id == 100
    assert method.reply_parameters.allow_sending_without_reply is True


async def test_new_inaccessible_message(
    safe_call: FakeSafeCall, inaccessible: InaccessibleMessage
) -> None:
    method = await Replacer(Plain()).new(inaccessible)
    assert safe_call.calls == []
    assert method.chat_id == 100
