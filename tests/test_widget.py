import dataclasses

import pytest

from aiogram_screens import Widget


def test_defaults() -> None:
    widget = Widget("<b>x</b>")
    assert widget.html == "<b>x</b>"
    assert widget.width is None
    assert widget.height is None
    assert widget.allow_queries is None


def test_optional_fields_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        Widget("<b>x</b>", 100)  # type: ignore[call-arg]


def test_widget_is_frozen() -> None:
    widget = Widget("<b>x</b>")
    with pytest.raises(dataclasses.FrozenInstanceError):
        widget.html = "y"  # type: ignore[misc]
