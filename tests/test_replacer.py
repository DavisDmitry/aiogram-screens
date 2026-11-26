from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from aiogram.methods import (
    DeleteMessage,
    EditMessageReplyMarkup,
    EditMessageText,
    SendMessage,
    SendWidget,
    TelegramMethod,
)
from aiogram.types import (
    Chat,
    DirectMessagesTopic,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    PhotoSize,
    RichMessage,
)
from aiogram.types import Widget as TelegramWidget

from aiogram_screens import (
    EditableTextMessageScreen,
    NewReplyParameters,
    Replacer,
    TextMessageScreen,
    Widget,
    WidgetScreen,
)

KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="ok")]]
)


class Plain(TextMessageScreen[str]):
    def create_text(self) -> str:
        return "plain"


class Editable(EditableTextMessageScreen[str]):
    def create_text(self) -> str:
        return "editable"

    def create_reply_markup(self) -> InlineKeyboardMarkup:
        return KEYBOARD


class WidgetScreenFixture(WidgetScreen):
    def create_widget(self) -> Widget:
        return Widget("<b>widget</b>", width=100, height=200, allow_queries=True)

    def create_caption(self) -> str:
        return "caption"


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


# kwargs of make_message() that turn it into a message sent by SendWidget.
WIDGET_MESSAGE_KWARGS: dict[str, Any] = {
    "text": None,
    "widget": TelegramWidget(html="<b>old</b>"),
}


# --- replace ---


async def test_replace_deletes_message(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).replace(make_message())
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendMessage)
    assert (method.chat_id, method.text) == (100, "plain")


async def test_replace_falls_back_to_removing_markup(
    safe_call: FakeSafeCall,
    make_message: Any,
) -> None:
    # When the old message can't be deleted, replace() at least removes its
    # reply markup; a widget message has no editable markup to remove.
    safe_call.failing.add(DeleteMessage)
    await Replacer(Plain()).replace(make_message())
    assert safe_call.types == [DeleteMessage, EditMessageReplyMarkup]


@pytest.mark.usefixtures("safe_call")
async def test_replace_copies_message_context(make_message: Any) -> None:
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


async def test_replace_widget(safe_call: FakeSafeCall, make_message: Any) -> None:
    method = await Replacer(WidgetScreenFixture()).replace(make_message())
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendWidget)
    assert method.chat_id == 100
    assert method.html == "<b>widget</b>"
    assert (method.width, method.height) == (100, 200)
    assert method.allow_queries is True
    assert method.caption == "caption"


@pytest.mark.usefixtures("safe_call")
async def test_replace_widget_copies_message_thread_id(
    make_message: Any,
) -> None:
    method = await Replacer(WidgetScreenFixture()).replace(
        make_message(message_thread_id=7)
    )
    assert isinstance(method, SendWidget)
    assert method.message_thread_id == 7


async def test_replace_widget_inaccessible_message(
    safe_call: FakeSafeCall, inaccessible: InaccessibleMessage
) -> None:
    method = await Replacer(WidgetScreenFixture()).replace(inaccessible)
    assert safe_call.calls == []
    assert isinstance(method, SendWidget)
    assert method.chat_id == 100


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


async def test_edit_or_replace_edits_rich_message(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    message = make_message(text=None, rich_message=RichMessage(blocks=[]))
    method = await Replacer(Editable()).edit_or_replace(message)
    assert safe_call.calls == []
    assert isinstance(method, EditMessageText)


async def test_edit_or_replace_replaces_media_message(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    # EditMessageText can't turn a media message into a text one.
    message = make_message(
        text=None,
        photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)],
        caption="old",
    )
    method = await Replacer(Editable()).edit_or_replace(message)
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendMessage)
    assert method.text == "editable"


async def test_edit_or_replace_replaces_plain_screen(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).edit_or_replace(make_message())
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendMessage)


@pytest.mark.usefixtures("safe_call")
async def test_edit_or_replace_replaces_inaccessible_message(
    inaccessible: InaccessibleMessage,
) -> None:
    method = await Replacer(Editable()).edit_or_replace(inaccessible)
    assert isinstance(method, SendMessage)
    assert method.text == "editable"


@pytest.mark.usefixtures("safe_call")
async def test_edit_or_replace_forwards_options_on_fallback(
    make_message: Any,
) -> None:
    method = await Replacer(Plain()).edit_or_replace(
        make_message(), parse_mode="HTML", link_preview_options=None
    )
    assert isinstance(method, SendMessage)
    assert method.parse_mode == "HTML"
    assert method.link_preview_options is None


@pytest.mark.parametrize(
    "message_kwargs",
    [
        pytest.param({}, id="text message"),
        pytest.param(WIDGET_MESSAGE_KWARGS, id="widget message"),
    ],
)
async def test_edit_or_replace_replaces_widget(
    safe_call: FakeSafeCall, make_message: Any, message_kwargs: dict[str, Any]
) -> None:
    # A widget screen can't be edited in place, regardless of the old message.
    method = await Replacer(WidgetScreenFixture()).edit_or_replace(
        make_message(**message_kwargs), parse_mode="HTML"
    )
    assert safe_call.types == [DeleteMessage]
    assert isinstance(method, SendWidget)
    assert (method.chat_id, method.html) == (100, "<b>widget</b>")
    assert method.parse_mode == "HTML"


# --- new ---


async def test_new_removes_old_markup(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(Plain()).new(make_message(message_thread_id=7))
    assert safe_call.types == [EditMessageReplyMarkup]
    assert method.chat_id == 100
    assert method.message_thread_id == 7
    assert method.reply_parameters is None


@pytest.mark.usefixtures("safe_call")
async def test_new_replies_to_old_message(make_message: Any) -> None:
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


async def test_new_widget_removes_old_markup(
    safe_call: FakeSafeCall, make_message: Any
) -> None:
    method = await Replacer(WidgetScreenFixture()).new(
        make_message(),
        reply_parameters=NewReplyParameters(allow_sending_without_reply=True),
    )
    assert safe_call.types == [EditMessageReplyMarkup]
    assert isinstance(method, SendWidget)
    assert method.chat_id == 100
    assert method.reply_parameters is not None
    assert method.reply_parameters.message_id == 42
    assert method.reply_parameters.chat_id == 100
    assert method.reply_parameters.allow_sending_without_reply is True


async def test_new_widget_inaccessible_message(
    safe_call: FakeSafeCall, inaccessible: InaccessibleMessage
) -> None:
    method = await Replacer(WidgetScreenFixture()).new(inaccessible)
    assert safe_call.calls == []
    assert isinstance(method, SendWidget)
    assert method.chat_id == 100
    assert method.reply_parameters is None


# The three methods share one guard against send contexts SendWidget doesn't
# have, so it is checked through every entry point.
_WIDGET_METHODS: dict[str, Callable[[Replacer[Any], Any], Awaitable[object]]] = {
    "replace": lambda replacer, message: replacer.replace(message),
    "edit_or_replace": lambda replacer, message: replacer.edit_or_replace(message),
    "new": lambda replacer, message: replacer.new(message),
}

_UNSUPPORTED_CONTEXTS = [
    pytest.param(
        {"business_connection_id": "biz"}, "business connection", id="business"
    ),
    pytest.param(
        {"direct_messages_topic": DirectMessagesTopic(topic_id=3)},
        "direct messages topic",
        id="topic",
    ),
]


@pytest.mark.parametrize(("context_kwargs", "error"), _UNSUPPORTED_CONTEXTS)
@pytest.mark.parametrize("method", _WIDGET_METHODS.values(), ids=list(_WIDGET_METHODS))
async def test_widget_methods_reject_unsupported_context(
    safe_call: FakeSafeCall,
    make_message: Any,
    method: Callable[[Replacer[Any], Any], Awaitable[object]],
    context_kwargs: dict[str, Any],
    error: str,
) -> None:
    # SendWidget has neither business_connection_id nor
    # direct_messages_topic_id fields.
    with pytest.raises(ValueError, match=error):
        await method(Replacer(WidgetScreenFixture()), make_message(**context_kwargs))
    # Refused before touching the old message, so it survives.
    assert safe_call.calls == []
