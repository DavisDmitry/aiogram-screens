import abc
from typing import (
    Any,
    ClassVar,
    Generic,
    NamedTuple,
    Self,
    TypeAlias,
    TypeVar,
    cast,
    final,
    overload,
)

from aiogram.client.default import Default
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendMessage,
    SendRichMessage,
)
from aiogram.types import (
    CallbackQuery,
    ChatIdUnion,
    EphemeralMessageParameters,
    InlineKeyboardMarkup,
    InputRichMessage,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
    ReplyParameters,
    SuggestedPostParameters,
)

from aiogram_screens._meta import FrozenScreenError, ScreenMeta

ScreenText: TypeAlias = str | InputRichMessage
# The text type a screen produces: str for regular messages, InputRichMessage
# for rich ones. It decides which method send() builds.
TextT = TypeVar("TextT", str, InputRichMessage)


class ScreenValues(NamedTuple):
    text: ScreenText
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None


# Kept outside ScreenMeta so dataclass_transform doesn't treat it as a field:
# fields are only collected from dataclass-like classes.
class _ScreenStorage:
    __slots__ = ("__screen_values__",)
    __screen_values__: ScreenValues


class BaseScreen(_ScreenStorage, Generic[TextT], metaclass=ScreenMeta):
    __screen_fields__: ClassVar[tuple[str, ...]]
    __screen_no_init__: ClassVar[frozenset[str]]
    __screen_defaults__: ClassVar[dict[str, Any]]

    # Construction lives in __new__ rather than __init__: mypy synthesizes
    # __init__ for every dataclass_transform subclass, which would clash
    # with a final __init__ here.
    @final
    def __new__(cls, **kwargs: Any) -> Self:
        no_init = cls.__screen_no_init__
        init_fields = tuple(f for f in cls.__screen_fields__ if f not in no_init)
        unexpected = tuple(k for k in kwargs if k not in init_fields)
        if unexpected:
            raise TypeError(
                f"{cls.__name__}() got unexpected keyword arguments: "
                + ", ".join(map(repr, unexpected))
            )
        defaults = cls.__screen_defaults__
        missing = tuple(f for f in init_fields if f not in kwargs and f not in defaults)
        if missing:
            raise TypeError(
                f"{cls.__name__}() missing required keyword arguments: "
                + ", ".join(map(repr, missing))
            )

        self = super().__new__(cls)
        for k, v in {**defaults, **kwargs}.items():
            object.__setattr__(self, k, v)
        # Screens are frozen: __post_init__ must use object.__setattr__
        # to assign attributes, just like in frozen dataclasses.
        self.__post_init__()
        unset = tuple(f for f in no_init if not hasattr(self, f))
        if unset:
            raise TypeError(
                f"{cls.__name__}.__post_init__() must set init=False fields: "
                + ", ".join(map(repr, sorted(unset)))
            )
        object.__setattr__(
            self,
            "__screen_values__",
            ScreenValues(self.create_text(), self.create_reply_markup()),
        )
        return self

    def __setattr__(self, name: str, value: Any) -> None:
        raise FrozenScreenError(f"cannot assign to field {name!r}")

    def __delattr__(self, name: str) -> None:
        raise FrozenScreenError(f"cannot delete field {name!r}")

    def __post_init__(self) -> None:
        return

    @abc.abstractmethod
    def create_text(self) -> TextT:
        pass

    def create_reply_markup(self) -> InlineKeyboardMarkup | ReplyKeyboardMarkup | None:
        return None


class MessageScreen(BaseScreen[TextT]):
    @overload
    def send(
        self: "MessageScreen[str]",
        chat_id: ChatIdUnion,
        *,
        business_connection_id: str | None = ...,
        message_thread_id: int | None = ...,
        direct_messages_topic_id: int | None = ...,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
        reply_parameters: ReplyParameters | None = ...,
        suggested_post_parameters: SuggestedPostParameters | None = ...,
        ephemeral_message_parameters: EphemeralMessageParameters | None = ...,
    ) -> SendMessage: ...
    @overload
    def send(
        self: "MessageScreen[InputRichMessage]",
        chat_id: ChatIdUnion,
        *,
        business_connection_id: str | None = ...,
        message_thread_id: int | None = ...,
        direct_messages_topic_id: int | None = ...,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
        reply_parameters: ReplyParameters | None = ...,
        suggested_post_parameters: SuggestedPostParameters | None = ...,
        ephemeral_message_parameters: EphemeralMessageParameters | None = ...,
    ) -> SendRichMessage: ...
    def send(
        self,
        chat_id: ChatIdUnion,
        *,
        business_connection_id: str | None = None,
        message_thread_id: int | None = None,
        direct_messages_topic_id: int | None = None,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
        reply_parameters: ReplyParameters | None = None,
        suggested_post_parameters: SuggestedPostParameters | None = None,
        ephemeral_message_parameters: EphemeralMessageParameters | None = None,
    ) -> SendMessage | SendRichMessage:
        text, reply_markup = self.__screen_values__
        if isinstance(text, InputRichMessage):
            return SendRichMessage(
                chat_id=chat_id,
                rich_message=text,
                business_connection_id=business_connection_id,
                message_thread_id=message_thread_id,
                direct_messages_topic_id=direct_messages_topic_id,
                disable_notification=disable_notification,
                protect_content=protect_content,
                allow_paid_broadcast=allow_paid_broadcast,
                message_effect_id=message_effect_id,
                suggested_post_parameters=suggested_post_parameters,
                reply_parameters=reply_parameters,
                reply_markup=reply_markup,
                ephemeral_message_parameters=ephemeral_message_parameters,
            )
        return SendMessage(
            chat_id=chat_id,
            text=text,
            business_connection_id=business_connection_id,
            message_thread_id=message_thread_id,
            direct_messages_topic_id=direct_messages_topic_id,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            suggested_post_parameters=suggested_post_parameters,
            reply_parameters=reply_parameters,
            reply_markup=reply_markup,
            ephemeral_message_parameters=ephemeral_message_parameters,
        )


class EditableMessageScreen(MessageScreen[TextT]):
    def create_reply_markup(self) -> InlineKeyboardMarkup | None:
        return None

    @overload
    def edit(
        self,
        *,
        message: Message,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
    ) -> EditMessageText: ...
    @overload
    def edit(
        self,
        *,
        chat_id: ChatIdUnion,
        message_id: int,
        business_connection_id: str | None = ...,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
    ) -> EditMessageText: ...
    @overload
    def edit(
        self,
        *,
        inline_message_id: str,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
    ) -> EditMessageText: ...
    def edit(
        self,
        message: Message | None = None,
        chat_id: ChatIdUnion | None = None,
        message_id: int | None = None,
        inline_message_id: str | None = None,
        business_connection_id: str | None = None,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
    ) -> EditMessageText:
        if (chat_id is None or message_id is None) and not inline_message_id:
            if message is None:
                raise ValueError(
                    "message or chat_id and message_id "
                    "or inline_message_id must be passed"
                )

            chat_id = message.chat.id
            message_id = message.message_id
            business_connection_id = message.business_connection_id

        content, reply_markup = cast(
            tuple[ScreenText, InlineKeyboardMarkup | None], self.__screen_values__
        )
        if isinstance(content, str):
            text = content
            rich_message = None
        else:
            text = None
            rich_message = content

        return EditMessageText(
            text=text,
            business_connection_id=business_connection_id,
            chat_id=chat_id,
            message_id=message_id,
            inline_message_id=inline_message_id,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            reply_markup=reply_markup,
            rich_message=rich_message,
        )


class CallbackQueryAnswerScreen(BaseScreen[str]):
    @abc.abstractmethod
    def create_text(self) -> str:
        pass

    @final
    def create_reply_markup(self) -> None:
        return None

    def answer(
        self,
        query_or_id: CallbackQuery | str,
        show_alert: bool | None = None,
        cache_time: int | None = None,
    ) -> AnswerCallbackQuery:
        text = cast(str, self.__screen_values__[0])

        if isinstance(query_or_id, CallbackQuery):
            return query_or_id.answer(
                text=text, show_alert=show_alert, cache_time=cache_time
            )

        return AnswerCallbackQuery(
            callback_query_id=query_or_id,
            text=text,
            show_alert=show_alert,
            cache_time=cache_time,
        )
