import abc
import re
import sys
from types import ModuleType
from typing import (
    Any,
    ClassVar,
    ForwardRef,
    NamedTuple,
    Self,
    TypeAlias,
    TypeVar,
    cast,
    dataclass_transform,
    final,
    get_origin,
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

ScreenText: TypeAlias = str | InputRichMessage


class FrozenScreenError(AttributeError):
    """Raised on an attempt to assign or delete an attribute of a screen."""


class ScreenValues(NamedTuple):
    text: ScreenText
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None


def _get_namespace_annotations(namespace: dict[str, Any]) -> dict[str, Any]:
    if "__annotations__" in namespace:
        return dict(namespace["__annotations__"])
    try:  # Python 3.14+: annotations are evaluated lazily (PEP 649)
        import annotationlib  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return {}
    annotate = annotationlib.get_annotate_from_class_namespace(namespace)
    if annotate is None:
        return {}
    return cast(
        dict[str, Any],
        annotationlib.call_annotate_function(annotate, annotationlib.Format.FORWARDREF),
    )


_MODULE_IDENTIFIER_RE = re.compile(r"^(?:\s*(\w+)\s*\.)?\s*(\w+)")


def _is_classvar(annotation: Any, module_name: str | None) -> bool:
    if isinstance(annotation, ForwardRef):
        annotation = annotation.__forward_arg__
    if isinstance(annotation, str):
        return _is_classvar_string(annotation, module_name)
    return annotation is ClassVar or get_origin(annotation) is ClassVar


def _is_classvar_string(annotation: str, module_name: str | None) -> bool:
    # Same approach as dataclasses: resolve the leading name of a string
    # annotation in the class's module instead of eval()-ing it. "CV[int]"
    # matches if the module has CV = ClassVar, "t.ClassVar[int]" if the module
    # has a module bound to t. Names bound only in the class body or only under
    # TYPE_CHECKING are not detected.
    match = _MODULE_IDENTIFIER_RE.match(annotation)
    module = sys.modules.get(module_name) if module_name else None
    if match is None or module is None:
        return False
    prefix, name = match.groups()
    namespace = vars(module)
    if prefix:
        prefix_module = namespace.get(prefix)
        if not isinstance(prefix_module, ModuleType):
            return False
        namespace = vars(prefix_module)
    return namespace.get(name) is ClassVar


_MISSING: Any = object()
_T = TypeVar("_T")


@final
class _FieldSpec(NamedTuple):
    default: Any
    init: bool


@overload
def field(*, default: _T, init: bool = True) -> _T: ...
@overload
def field(*, init: bool = True) -> Any: ...
def field(*, default: Any = _MISSING, init: bool = True) -> Any:
    """Field specifier for screens, recognized by type checkers (PEP 681).

    ``init=False`` excludes the field from the constructor: give it a
    ``default`` or assign it in ``__post_init__`` via ``object.__setattr__``.
    """
    return _FieldSpec(default, init)


# Class keywords that type checkers interpret for dataclass_transform classes.
# Screens don't support them, so reject them instead of letting linters assume
# e.g. frozen=False while the runtime stays frozen.
_DATACLASS_CLASS_KWARGS = frozenset(
    {
        "init",
        "repr",
        "eq",
        "order",
        "unsafe_hash",
        "frozen",
        "match_args",
        "kw_only",
        "slots",
        "weakref_slot",
    }
)


@dataclass_transform(
    kw_only_default=True, frozen_default=True, field_specifiers=(field,)
)
class ScreenMeta(abc.ABCMeta):
    def __new__(
        mcls: type["ScreenMeta"],
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        /,
        **kwargs: Any,
    ) -> "ScreenMeta":
        unsupported = sorted(_DATACLASS_CLASS_KWARGS.intersection(kwargs))
        if unsupported:
            raise TypeError(
                f"{name}: screen classes don't support class keywords: "
                + ", ".join(map(repr, unsupported))
            )
        if "__init__" in namespace and any(isinstance(b, ScreenMeta) for b in bases):
            raise TypeError(
                f"{name} must not define __init__, override __post_init__ instead"
            )
        if "__slots__" in namespace:
            raise TypeError(
                f"{name} must not define __slots__, they are generated from fields"
            )

        fields = tuple(
            f
            for f, annotation in _get_namespace_annotations(namespace).items()
            if not _is_classvar(annotation, namespace.get("__module__"))
        )
        inherited_fields: dict[str, None] = {}
        no_init: set[str] = set()
        # Default values can't live in the class namespace alongside slots
        # with the same name, so move them into a separate mapping.
        defaults: dict[str, Any] = {}
        for base in reversed(bases):
            inherited_fields.update(
                dict.fromkeys(getattr(base, "__screen_fields__", ()))
            )
            no_init.update(getattr(base, "__screen_no_init__", ()))
            defaults.update(getattr(base, "__screen_defaults__", {}))
        for f in fields:
            value = namespace.pop(f, _MISSING)
            init = True
            if isinstance(value, _FieldSpec):
                init = value.init
                value = value.default
            if value is not _MISSING:
                defaults[f] = value
            # A re-declared field takes the init flag of the latest declaration.
            if init:
                no_init.discard(f)
            else:
                no_init.add(f)
        # Re-declared parent fields already have a slot in the parent.
        namespace["__slots__"] = tuple(f for f in fields if f not in inherited_fields)
        namespace["__screen_fields__"] = tuple(
            {**inherited_fields, **dict.fromkeys(fields)}
        )
        namespace["__screen_no_init__"] = frozenset(no_init)
        namespace["__screen_defaults__"] = defaults
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        return cls


# Kept outside ScreenMeta so dataclass_transform doesn't treat it as a field:
# fields are only collected from dataclass-like classes.
class _ScreenStorage:
    __slots__ = ("__screen_values__",)
    __screen_values__: ScreenValues


class BaseScreen(_ScreenStorage, metaclass=ScreenMeta):
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
    def create_text(self) -> ScreenText:
        pass

    def create_reply_markup(self) -> InlineKeyboardMarkup | ReplyKeyboardMarkup | None:
        return None


class MessageScreen(BaseScreen):
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


class EditableMessageScreen(MessageScreen):
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


class CallbackQueryAnswerScreen(BaseScreen):
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
