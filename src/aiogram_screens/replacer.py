from dataclasses import dataclass
from typing import Final, Generic, TypedDict, TypeVar

from aiogram.client.default import Default
from aiogram.methods import EditMessageText, SendMessage, SendRichMessage
from aiogram.types import (
    InaccessibleMessage,
    LinkPreviewOptions,
    Message,
    ReplyParameters,
    SuggestedPostParameters,
)

from aiogram_screens.safe import safe_call
from aiogram_screens.screens import EditableMessageScreen, MessageScreen

S = TypeVar("S", bound=MessageScreen)


@dataclass(frozen=True, kw_only=True, slots=True)
class NewReplyParameters:
    allow_sending_without_reply: bool | Default | None = Default(
        "allow_sending_without_reply"
    )


class MessageParams(TypedDict, total=False):
    business_connection_id: str | None
    message_thread_id: int | None
    direct_messages_topic_id: int | None


class Replacer(Generic[S]):
    __slots__ = ("screen",)

    def __init__(self, screen: S):
        self.screen: Final[S] = screen

    @staticmethod
    def _get_message_params(message: Message, params: MessageParams) -> MessageParams:
        params["business_connection_id"] = message.business_connection_id
        params["message_thread_id"] = message.message_thread_id
        if message.direct_messages_topic:
            params["direct_messages_topic_id"] = message.direct_messages_topic.topic_id
        return params

    async def replace(
        self,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
    ) -> SendMessage | SendRichMessage:
        message_params = MessageParams()

        if isinstance(message, Message):
            success, _ = await safe_call(message.delete())
            if not success:
                await safe_call(message.delete_reply_markup())
            self._get_message_params(message, message_params)

        return self.screen.send(
            message.chat.id,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            **message_params,
        )

    async def edit_or_replace(
        self,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
    ) -> SendMessage | SendRichMessage | EditMessageText:
        if isinstance(message, InaccessibleMessage) or not isinstance(
            self.screen, EditableMessageScreen
        ):
            return await self.replace(
                message,
                parse_mode=parse_mode,
                link_preview_options=link_preview_options,
                disable_notification=disable_notification,
                protect_content=protect_content,
                allow_paid_broadcast=allow_paid_broadcast,
                message_effect_id=message_effect_id,
            )
        return self.screen.edit(
            message=message,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
        )

    async def new(
        self,
        message: Message | InaccessibleMessage,
        *,
        parse_mode: str | Default | None = Default("parse_mode"),
        link_preview_options: LinkPreviewOptions | Default | None = Default(
            "link_preview"
        ),
        disable_notification: bool | None = None,
        protect_content: bool | Default | None = Default("protect_content"),
        allow_paid_broadcast: bool | None = None,
        message_effect_id: str | None = None,
        reply_parameters: NewReplyParameters | None = None,
        suggested_post_parameters: SuggestedPostParameters | None = None,
    ) -> SendMessage | SendRichMessage:
        message_params = MessageParams()

        if isinstance(message, Message):
            await safe_call(message.delete_reply_markup())
            self._get_message_params(message, message_params)

        return self.screen.send(
            message.chat.id,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
            disable_notification=disable_notification,
            protect_content=protect_content,
            allow_paid_broadcast=allow_paid_broadcast,
            message_effect_id=message_effect_id,
            reply_parameters=(
                ReplyParameters(
                    message_id=message.message_id,
                    chat_id=message.chat.id,
                    allow_sending_without_reply=(
                        reply_parameters.allow_sending_without_reply
                    ),
                )
                if reply_parameters
                else None
            ),
            suggested_post_parameters=suggested_post_parameters,
            **message_params,
        )
