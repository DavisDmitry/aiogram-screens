"""Screens declared with string annotations (PEP 563)."""

from __future__ import annotations

import typing
import typing as t
from typing import ClassVar
from typing import ClassVar as CV
from typing import ForwardRef

import pytest
from aiogram.methods import SendMessage

from aiogram_screens import MessageScreen
from aiogram_screens.screens import _is_classvar

AliasedClassVar = ClassVar
NotClassVar = int


class Prefixed(MessageScreen):
    prefix: ClassVar[str] = ">"
    suffix: typing.ClassVar[str] = "<"
    name: str
    count: int = 1

    def create_text(self) -> str:
        return f"{self.prefix}{self.name} x{self.count}{self.suffix}"


def test_classvar_is_not_a_field() -> None:
    assert Prefixed.__annotations__["prefix"] == "ClassVar[str]"
    assert Prefixed.__screen_fields__ == ("name", "count")


def test_fields_and_defaults() -> None:
    method = Prefixed(name="a").send(1)
    assert isinstance(method, SendMessage)
    assert method.text == ">a x1<"
    assert Prefixed(name="a", count=2).count == 2


def test_classvar_aliases() -> None:
    class Aliased(MessageScreen):
        imported_as: CV[int] = 1
        module_alias: t.ClassVar[int] = 2
        # Type checkers reject a plain assignment as a ClassVar alias,
        # but the runtime resolves it the same way dataclasses do.
        assigned: AliasedClassVar[int] = 3  # type: ignore[valid-type]
        bare: ClassVar = 4
        name: str

        def create_text(self) -> str:
            return self.name

    assert Aliased.__screen_fields__ == ("name",)
    assert (Aliased.imported_as, Aliased.module_alias, Aliased.assigned) == (1, 2, 3)


@pytest.mark.parametrize(
    "annotation",
    [
        "ClassVar[int]",
        " ClassVar [int]",
        "CV[int]",
        "t.ClassVar[int]",
        "typing.ClassVar[int]",
        "AliasedClassVar",
        ForwardRef("CV[int]"),
    ],
)
def test_is_classvar(annotation: str | ForwardRef) -> None:
    assert _is_classvar(annotation, __name__)


@pytest.mark.parametrize(
    "annotation",
    [
        "int",
        "NotClassVar",
        "ClassVarLike[int]",  # not bound in the module
        "NotClassVar.ClassVar[int]",  # prefix is not a module
        "missing.ClassVar[int]",
        "list[ClassVar[int]]",
        ForwardRef("int"),
    ],
)
def test_is_not_classvar(annotation: str | ForwardRef) -> None:
    assert not _is_classvar(annotation, __name__)


def test_unknown_module() -> None:
    assert not _is_classvar("ClassVar[int]", None)
    assert not _is_classvar("ClassVar[int]", "no.such.module")
