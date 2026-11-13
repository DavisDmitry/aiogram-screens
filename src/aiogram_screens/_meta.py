"""Dataclass-like machinery behind screens: fields, defaults and freezing.

Independent from aiogram: it only knows about annotations and field specifiers.
"""

import abc
import re
import sys
from types import ModuleType
from typing import (
    Any,
    ClassVar,
    ForwardRef,
    NamedTuple,
    TypeVar,
    cast,
    dataclass_transform,
    final,
    get_origin,
    overload,
)


class FrozenScreenError(AttributeError):
    """Raised on an attempt to assign or delete an attribute of a screen."""


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
