from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Generic, TypedDict, TypeVar, overload

from aiogram.client.default import Default
from aiogram.enums import ContentType
from aiogram.methods import (
    DeleteBusinessMessages,
    DeleteMessage,
    EditMessageText,
    SendMessage,
    SendRichMessage,
    SendWidget,
)
from aiogram.types import (
    InaccessibleMessage,
    InputRichMessage,
    LinkPreviewOptions,
    Message,
    ReplyParameters,
    SuggestedPostParameters,
)

from aiogram_screens.safe import safe_call
from aiogram_screens.screens import (
    EditableTextMessageScreen,
    TextMessageScreen,
    WidgetScreen,
)

# Messages that EditMessageText can edit. A media message can't become a text
# one by editing, so text screens replace it instead.
_TEXT_CONTENT_TYPES = frozenset({ContentType.TEXT, ContentType.RICH_MESSAGE})

# Screens Replacer can send. A widget message can't be edited in place, so
# edit_or_replace() always replaces it.
SendableScreen = TextMessageScreen[Any] | WidgetScreen

# Covariant, so Replacer[Greeting] matches the Replacer[TextMessageScreen[str]]
# overloads below; the screen is read-only, so covariance is safe.
S_co = TypeVar("S_co", bound=SendableScreen, covariant=True)


@dataclass(frozen=True, kw_only=True, slots=True)
class NewReplyParameters:
    allow_sending_without_reply: bool | Default | None = Default(
        "allow_sending_without_reply"
    )


class MessageParams(TypedDict, total=False):
    business_connection_id: str | None
    message_thread_id: int | None
    direct_messages_topic_id: int | None


class Replacer(Generic[S_co]):
    __slots__ = ("screen",)

    def __init__(self, screen: S_co) -> None:
        self.screen: Final[S_co] = screen

    @staticmethod
    def _get_message_params(message: Message, params: MessageParams) -> MessageParams:
        params["business_connection_id"] = message.business_connection_id
        params["message_thread_id"] = message.message_thread_id
        if message.direct_messages_topic:
            params["direct_messages_topic_id"] = message.direct_messages_topic.topic_id
        return params

    @staticmethod
    def _check_widget_context(message: Message | InaccessibleMessage) -> None:
        """SendWidget can carry neither a business connection nor a topic."""
        if not isinstance(message, Message):
            return
        if message.business_connection_id:
            raise ValueError("a widget screen can't be sent to a business connection")
        if message.direct_messages_topic:
            raise ValueError("a widget screen can't be sent to a direct messages topic")

    @staticmethod
    def _reply_parameters(
        message: Message | InaccessibleMessage,
        reply_parameters: NewReplyParameters | None,
    ) -> ReplyParameters | None:
        if not reply_parameters:
            return None
        return ReplyParameters(
            message_id=message.message_id,
            chat_id=message.chat.id,
            allow_sending_without_reply=reply_parameters.allow_sending_without_reply,
        )

    async def _delete_message(
        self, message: Message | InaccessibleMessage
    ) -> MessageParams:
        """Delete the old message and collect the params of the new one."""
        message_params = MessageParams()

        if isinstance(message, Message):
            method: DeleteMessage | DeleteBusinessMessages
            if message.business_connection_id:
                method = DeleteBusinessMessages(
                    business_connection_id=message.business_connection_id,
                    message_ids=[message.message_id],
                )
            else:
                method = message.delete()
            success, _ = await safe_call(method)
            if not success:
                await safe_call(message.delete_reply_markup())
            self._get_message_params(message, message_params)

        return message_params

    async def _replace_text(
        self,
        screen: TextMessageScreen[Any],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None,
        link_preview_options: LinkPreviewOptions | Default | None,
        disable_notification: bool | None,
        protect_content: bool | Default | None,
        allow_paid_broadcast: bool | None,
        message_effect_id: str | None,
    ) -> SendMessage | SendRichMessage:
        message_params = await self._delete_message(message)

        return screen.send(
            message.chat.id,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            **message_params,
        )

    @staticmethod
    def _send_widget(
        screen: WidgetScreen,
        message: Message | InaccessibleMessage,
        message_params: MessageParams,
        *,
        parse_mode: str | Default | None,
        show_caption_above_media: bool | Default | None,
        disable_notification: bool | None,
        protect_content: bool | Default | None,
        allow_paid_broadcast: bool | None,
        message_effect_id: str | None,
        reply_parameters: ReplyParameters | None = None,
    ) -> SendWidget:
        # parse_mode of a widget screen governs the caption, not the widget
        # body: the body is always HTML.
        return screen.send(
            message.chat.id,
            message_thread_id=message_params.get("message_thread_id"),
            parse_mode=parse_mode,
            show_caption_above_media=show_caption_above_media,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            reply_parameters=reply_parameters,
        )

    async def _replace_widget(
        self,
        screen: WidgetScreen,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None,
        show_caption_above_media: bool | Default | None,
        disable_notification: bool | None,
        protect_content: bool | Default | None,
        allow_paid_broadcast: bool | None,
        message_effect_id: str | None,
    ) -> SendWidget:
        # Checked before deleting: a refused send must not lose the old message.
        self._check_widget_context(message)
        message_params = await self._delete_message(message)

        return self._send_widget(
            screen,
            message,
            message_params,
            parse_mode=parse_mode,
            show_caption_above_media=show_caption_above_media,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
        )

    async def _new_widget(
        self,
        screen: WidgetScreen,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None,
        show_caption_above_media: bool | Default | None,
        disable_notification: bool | None,
        protect_content: bool | Default | None,
        allow_paid_broadcast: bool | None,
        message_effect_id: str | None,
        reply_parameters: NewReplyParameters | None,
    ) -> SendWidget:
        self._check_widget_context(message)

        message_params = MessageParams()
        if isinstance(message, Message):
            await safe_call(message.delete_reply_markup())
            self._get_message_params(message, message_params)

        return self._send_widget(
            screen,
            message,
            message_params,
            parse_mode=parse_mode,
            show_caption_above_media=show_caption_above_media,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            reply_parameters=self._reply_parameters(message, reply_parameters),
        )

    @overload
    async def replace(
        self: Replacer[TextMessageScreen[str]],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
    ) -> SendMessage: ...
    @overload
    async def replace(
        self: Replacer[TextMessageScreen[InputRichMessage]],
        message: Message | InaccessibleMessage,
        *,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
    ) -> SendRichMessage: ...
    @overload
    async def replace(
        self: Replacer[WidgetScreen],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = ...,
        show_caption_above_media: bool | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
    ) -> SendWidget: ...
    async def replace(
        self,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        show_caption_above_media: bool | Default | None = Default(
            "show_caption_above_media"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
    ) -> SendMessage | SendRichMessage | SendWidget:
        screen = self.screen
        if isinstance(screen, WidgetScreen):
            return await self._replace_widget(
                screen,
                message,
                parse_mode=parse_mode,
                show_caption_above_media=show_caption_above_media,
                disable_notification=disable_notification,
                protect_content=protect_content,
                allow_paid_broadcast=allow_paid_broadcast,
                message_effect_id=message_effect_id,
            )
        return await self._replace_text(
            screen,
            message,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
        )

    @overload
    async def edit_or_replace(
        self: Replacer[TextMessageScreen[str]],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
    ) -> SendMessage | EditMessageText: ...
    @overload
    async def edit_or_replace(
        self: Replacer[TextMessageScreen[InputRichMessage]],
        message: Message | InaccessibleMessage,
        *,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
    ) -> SendRichMessage | EditMessageText: ...
    @overload
    async def edit_or_replace(
        self: Replacer[WidgetScreen],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = ...,
        show_caption_above_media: bool | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
    ) -> SendWidget: ...
    async def edit_or_replace(
        self,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        show_caption_above_media: bool | Default | None = Default(
            "show_caption_above_media"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
    ) -> SendMessage | SendRichMessage | EditMessageText | SendWidget:
        screen = self.screen
        if isinstance(screen, WidgetScreen):
            return await self._replace_widget(
                screen,
                message,
                parse_mode=parse_mode,
                show_caption_above_media=show_caption_above_media,
                disable_notification=disable_notification,
                protect_content=protect_content,
                allow_paid_broadcast=allow_paid_broadcast,
                message_effect_id=message_effect_id,
            )
        if (
            isinstance(message, InaccessibleMessage)
            or message.content_type not in _TEXT_CONTENT_TYPES
            or not isinstance(screen, EditableTextMessageScreen)
        ):
            return await self._replace_text(
                screen,
                message,
                parse_mode=parse_mode,
                link_preview_options=link_preview_options,
                disable_notification=disable_notification,
                protect_content=protect_content,
                allow_paid_broadcast=allow_paid_broadcast,
                message_effect_id=message_effect_id,
            )
        return screen.edit(
            message=message,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
        )

    @overload
    async def new(
        self: Replacer[TextMessageScreen[str]],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = ...,
        link_preview_options: LinkPreviewOptions | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
        reply_parameters: NewReplyParameters | None = ...,
        suggested_post_parameters: SuggestedPostParameters | None = ...,
    ) -> SendMessage: ...
    @overload
    async def new(
        self: Replacer[TextMessageScreen[InputRichMessage]],
        message: Message | InaccessibleMessage,
        *,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
        reply_parameters: NewReplyParameters | None = ...,
        suggested_post_parameters: SuggestedPostParameters | None = ...,
    ) -> SendRichMessage: ...
    @overload
    async def new(
        self: Replacer[WidgetScreen],
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = ...,
        show_caption_above_media: bool | Default | None = ...,
        disable_notification: bool | None = ...,
        protect_content: bool | Default | None = ...,
        allow_paid_broadcast: bool | None = ...,
        message_effect_id: str | None = ...,
        reply_parameters: NewReplyParameters | None = ...,
    ) -> SendWidget: ...
    async def new(
        self,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        show_caption_above_media: bool | Default | None = Default(
            "show_caption_above_media"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
        reply_parameters: NewReplyParameters | None = None,
        suggested_post_parameters: SuggestedPostParameters | None = None,
    ) -> SendMessage | SendRichMessage | SendWidget:
        screen = self.screen
        if isinstance(screen, WidgetScreen):
            return await self._new_widget(
                screen,
                message,
                parse_mode=parse_mode,
                show_caption_above_media=show_caption_above_media,
                disable_notification=disable_notification,
                protect_content=protect_content,
                allow_paid_broadcast=allow_paid_broadcast,
                message_effect_id=message_effect_id,
                reply_parameters=reply_parameters,
            )

        message_params = MessageParams()
        if isinstance(message, Message):
            await safe_call(message.delete_reply_markup())
            self._get_message_params(message, message_params)

        return screen.send(
            message.chat.id,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            reply_parameters=self._reply_parameters(message, reply_parameters),
            suggested_post_parameters=suggested_post_parameters,
            **message_params,
        )
