from typing import Any, ClassVar

import pytest
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    SendRichMessage,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    User,
)

from aiogram_screens import (
    CallbackQueryAnswerScreen,
    EditableMessageScreen,
    FrozenScreenError,
    MessageScreen,
    field,
)
from aiogram_screens._meta import ScreenMeta

KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="ok")]]
)


def sent_text(screen: MessageScreen[str]) -> str:
    method = screen.send(1)
    assert isinstance(method, SendMessage)
    return method.text


class Greeting(MessageScreen[str]):
    name: str
    count: int = 1

    def create_text(self) -> str:
        return f"{self.name} x{self.count}"


class Menu(EditableMessageScreen[str]):
    title: str

    def create_text(self) -> str:
        return self.title

    def create_reply_markup(self) -> InlineKeyboardMarkup:
        return KEYBOARD


class Pong(CallbackQueryAnswerScreen):
    def create_text(self) -> str:
        return "pong"


# --- fields and construction ---


def test_fields_and_defaults() -> None:
    screen = Greeting(name="a")
    assert (screen.name, screen.count) == ("a", 1)
    assert Greeting(name="a", count=3).count == 3
    assert Greeting.__screen_fields__ == ("name", "count")
    assert Greeting.__dict__["__slots__"] == ("name", "count")


def test_no_instance_dict() -> None:
    assert not hasattr(Greeting(name="a"), "__dict__")


def test_missing_required_field() -> None:
    with pytest.raises(TypeError, match="missing required keyword arguments: 'name'"):
        Greeting()  # type: ignore[call-arg]


def test_unexpected_field() -> None:
    with pytest.raises(TypeError, match="unexpected keyword arguments: 'nope'"):
        Greeting(name="a", nope=1)  # type: ignore[call-arg]


def test_screen_values_is_not_a_field() -> None:
    with pytest.raises(TypeError, match="'__screen_values__'"):
        Greeting(name="a", __screen_values__=None)  # type: ignore[call-arg]


def test_classvar_is_not_a_field() -> None:
    class WithClassVar(MessageScreen[str]):
        prefix: ClassVar[str] = ">"
        name: str

        def create_text(self) -> str:
            return self.prefix + self.name

    assert WithClassVar.__screen_fields__ == ("name",)
    assert sent_text(WithClassVar(name="a")) == ">a"


def test_inheritance_and_redeclared_default() -> None:
    class Child(Greeting):
        count: int = 5
        extra: str = "e"

    screen = Child(name="b")
    assert (screen.name, screen.count, screen.extra) == ("b", 5, "e")
    assert Child.__screen_fields__ == ("name", "count", "extra")
    # The re-declared field reuses the parent's slot.
    assert Child.__dict__["__slots__"] == ("extra",)


@pytest.mark.parametrize("slots", [(), ("extra",)])
def test_slots_are_forbidden(slots: tuple[str, ...]) -> None:
    with pytest.raises(TypeError, match="must not define __slots__"):

        class Child(Greeting):
            __slots__ = slots
            extra: int


def test_abstract_create_text() -> None:
    class NoText(MessageScreen[str]):
        pass

    with pytest.raises(TypeError, match="abstract"):
        NoText()  # type: ignore[abstract]


def test_values_are_computed_once() -> None:
    calls: list[str] = []

    class Counted(MessageScreen[str]):
        def create_text(self) -> str:
            calls.append("text")
            return "t"

    screen = Counted()
    screen.send(1)
    screen.send(2)
    assert calls == ["text"]


def test_post_init_runs_before_create_text() -> None:
    class WithPostInit(MessageScreen[str]):
        name: str

        def __post_init__(self) -> None:
            object.__setattr__(self, "name", self.name.upper())

        def create_text(self) -> str:
            return self.name

    assert sent_text(WithPostInit(name="a")) == "A"


# --- frozen ---


def test_assign_is_forbidden() -> None:
    screen = Greeting(name="a")
    with pytest.raises(FrozenScreenError, match="'name'"):
        screen.name = "b"  # type: ignore[misc]
    assert screen.name == "a"


def test_delete_is_forbidden() -> None:
    screen = Greeting(name="a")
    with pytest.raises(FrozenScreenError, match="'name'"):
        del screen.name


def test_frozen_error_is_attribute_error() -> None:
    assert issubclass(FrozenScreenError, AttributeError)


# --- class definition rules ---


def test_init_is_forbidden() -> None:
    with pytest.raises(TypeError, match="must not define __init__"):

        class WithInit(MessageScreen[str]):
            def __init__(self) -> None:
                pass

            def create_text(self) -> str:
                return ""


@pytest.mark.parametrize("keyword", ["frozen", "eq", "order", "kw_only", "slots"])
def test_dataclass_class_keywords_are_rejected(keyword: str) -> None:
    with pytest.raises(TypeError, match=f"class keywords: '{keyword}'"):
        ScreenMeta("Bad", (MessageScreen,), {}, **{keyword: True})


def test_init_subclass_keywords_pass_through() -> None:
    class Tagged(MessageScreen[str]):
        tag: ClassVar[str] = ""

        def __init_subclass__(cls, tag: str = "", **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)
            cls.tag = tag

        def create_text(self) -> str:
            return self.tag

    class Child(Tagged, tag="ok"):
        pass

    assert sent_text(Child()) == "ok"


# --- field(init=False) ---


class Computed(MessageScreen[str]):
    name: str
    greeting: str = field(init=False)
    tag: str = field(default="t", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "greeting", f"hi {self.name}")

    def create_text(self) -> str:
        return f"{self.greeting} [{self.tag}]"


def test_init_false_field_is_set_in_post_init() -> None:
    assert sent_text(Computed(name="a")) == "hi a [t]"


@pytest.mark.parametrize("name", ["greeting", "tag"])
def test_init_false_field_is_not_accepted(name: str) -> None:
    with pytest.raises(TypeError, match=f"unexpected keyword arguments: '{name}'"):
        Computed(name="a", **{name: "x"})


def test_init_false_field_must_be_set() -> None:
    class Broken(MessageScreen[str]):
        value: int = field(init=False)

        def create_text(self) -> str:
            return ""

    with pytest.raises(TypeError, match="must set init=False fields: 'value'"):
        Broken()


def test_redeclared_field_returns_to_init() -> None:
    class Child(Computed):
        tag: str = "c"

    assert sent_text(Child(name="a", tag="z")) == "hi a [z]"
    assert Child(name="a").tag == "c"


def test_field_with_default_only() -> None:
    class WithField(MessageScreen[str]):
        count: int = field(default=3)

        def create_text(self) -> str:
            return str(self.count)

    assert WithField().count == 3
    assert WithField(count=4).count == 4


# --- MessageScreen.send ---


def test_send_text() -> None:
    method = Menu(title="t").send(
        1, message_thread_id=7, business_connection_id="b", parse_mode="HTML"
    )
    assert isinstance(method, SendMessage)
    assert method.chat_id == 1
    assert method.text == "t"
    assert method.reply_markup == KEYBOARD
    assert method.message_thread_id == 7
    assert method.business_connection_id == "b"
    assert method.parse_mode == "HTML"


def test_send_without_markup() -> None:
    method = Greeting(name="a").send(1)
    assert isinstance(method, SendMessage)
    assert method.reply_markup is None


def test_send_rich_message() -> None:
    rich = InputRichMessage(html="<b>hi</b>")

    class Rich(MessageScreen[InputRichMessage]):
        def create_text(self) -> InputRichMessage:
            return rich

    method = Rich().send(1, direct_messages_topic_id=3)
    assert isinstance(method, SendRichMessage)
    assert method.rich_message == rich
    assert method.direct_messages_topic_id == 3


# --- EditableMessageScreen.edit ---


def test_edit_by_message(make_message: Any) -> None:
    message = make_message(business_connection_id="biz")
    method = Menu(title="t").edit(message=message)
    assert isinstance(method, EditMessageText)
    assert (method.chat_id, method.message_id) == (100, 42)
    assert method.business_connection_id == "biz"
    assert method.text == "t"
    assert method.rich_message is None
    assert method.reply_markup == KEYBOARD


def test_edit_by_ids() -> None:
    method = Menu(title="t").edit(chat_id=1, message_id=2, business_connection_id="b")
    assert (method.chat_id, method.message_id) == (1, 2)
    assert method.business_connection_id == "b"
    assert method.inline_message_id is None


def test_edit_by_inline_message_id() -> None:
    method = Menu(title="t").edit(inline_message_id="inline")
    assert method.inline_message_id == "inline"
    assert method.chat_id is None
    assert method.message_id is None


def test_edit_without_target() -> None:
    with pytest.raises(ValueError, match="must be passed"):
        Menu(title="t").edit()  # type: ignore[call-overload]


def test_edit_rich_message() -> None:
    rich = InputRichMessage(html="<b>hi</b>")

    class Rich(EditableMessageScreen[InputRichMessage]):
        def create_text(self) -> InputRichMessage:
            return rich

    method = Rich().edit(chat_id=1, message_id=2)
    assert method.text is None
    assert method.rich_message == rich


# --- CallbackQueryAnswerScreen.answer ---


def test_answer_by_id() -> None:
    method = Pong().answer("query-id", show_alert=True, cache_time=5)
    assert isinstance(method, AnswerCallbackQuery)
    assert method.callback_query_id == "query-id"
    assert method.text == "pong"
    assert method.show_alert is True
    assert method.cache_time == 5


def test_answer_by_query() -> None:
    query = CallbackQuery(
        id="query-id",
        from_user=User(id=1, is_bot=False, first_name="u"),
        chat_instance="ci",
    )
    method = Pong().answer(query)
    assert isinstance(method, AnswerCallbackQuery)
    assert method.callback_query_id == "query-id"
    assert method.text == "pong"
