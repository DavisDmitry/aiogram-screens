# aiogram-screens

[![codecov](https://codecov.io/gh/DavisDmitry/aiogram-screens/graph/badge.svg)](https://codecov.io/gh/DavisDmitry/aiogram-screens)

Declarative screens for [aiogram 3](https://github.com/aiogram/aiogram) bots.

A **screen** is a small frozen class that describes one bot message: its fields
are the data, `create_text()` and `create_reply_markup()` turn that data into a
message. A screen doesn't send anything by itself — it builds aiogram methods
(`SendMessage`, `EditMessageText`, …) that you return from a handler or await
with a bot.

```python
from aiogram_screens import MessageScreen


class Welcome(MessageScreen):
    name: str

    def create_text(self) -> str:
        return f"Hello, {self.name}!"


@router.message(CommandStart())
async def start(message: Message) -> SendMessage | SendRichMessage:
    return Welcome(name=message.from_user.full_name).send(message.chat.id)
```

## Installation

The package is not published on PyPI yet. Install it from GitHub:

```sh
uv add git+https://github.com/DavisDmitry/aiogram-screens.git
# or
pip install git+https://github.com/DavisDmitry/aiogram-screens.git
```

To pin a specific commit or tag, append it after `@`:

```sh
uv add git+https://github.com/DavisDmitry/aiogram-screens.git@<commit-or-tag>
```

Requires Python 3.11+ and aiogram 3.31+.

## Screens

| Class | Builds | Use for |
|---|---|---|
| `MessageScreen` | `send()` → `SendMessage` / `SendRichMessage` | Messages that are only sent |
| `EditableMessageScreen` | `send()`, `edit()` → `EditMessageText` | Messages that are sent and later edited in place |
| `CallbackQueryAnswerScreen` | `answer()` → `AnswerCallbackQuery` | Callback query notifications and alerts |

`create_text()` returns either a `str` or an `InputRichMessage`; for a rich
message `send()` builds `SendRichMessage` instead of `SendMessage`.
`create_reply_markup()` is optional and returns `None` by default.

### Fields

Screens are declared like dataclasses: annotated class attributes become
keyword-only constructor arguments, values become defaults.

```python
from typing import ClassVar

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from aiogram_screens import EditableMessageScreen


class Counter(EditableMessageScreen):
    title: ClassVar[str] = "Counter"  # ClassVar is not a field
    value: int = 0

    def create_text(self) -> str:
        return f"{self.title}: {self.value}"

    def create_reply_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="+1", callback_data=f"inc:{self.value}")]
            ]
        )


Counter()            # value=0
Counter(value=5)     # value=5
Counter(valeu=5)     # TypeError: Counter() got unexpected keyword arguments: 'valeu'
```

Fields are inherited, and a subclass can re-declare a field to change its
default. Missing required fields and unknown arguments raise `TypeError`.

Mutable defaults (`items: list[str] = []`) are shared between instances, as in
plain classes — prefer immutable ones such as `tuple` or `frozenset`.

### Screens are frozen

The text and the markup are computed **once**, when the screen is created. To
keep them in sync with the fields, screens are immutable: assigning or deleting
an attribute raises `FrozenScreenError` (a subclass of `AttributeError`). To
show different data, create a new screen.

Screens must not define `__slots__` — they are generated from the fields, so
instances have no `__dict__`.

Screens must not define `__init__`. Use `__post_init__` for extra setup; it runs
after the fields are assigned and before `create_text()`. Like in frozen
dataclasses, assign attributes there with `object.__setattr__`.

Dataclass class keywords (`frozen=False`, `eq=True`, `order=True`, …) are not
supported and raise `TypeError`. Other class keywords are passed to
`__init_subclass__` as usual.

### Computed fields

`field(init=False)` excludes a field from the constructor. Give it a `default`,
or assign it in `__post_init__`; a screen that leaves such a field unset raises
`TypeError`.

```python
from aiogram_screens import MessageScreen, field


class Order(MessageScreen):
    price: int
    quantity: int
    total: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "total", self.price * self.quantity)

    def create_text(self) -> str:
        return f"{self.quantity} × {self.price} = {self.total}"


Order(price=10, quantity=3)            # "3 × 10 = 30"
Order(price=10, quantity=3, total=1)   # TypeError
```

`field()` is a PEP 681 field specifier, so mypy and pyright understand it too:
both report `total=1` as an unexpected argument. Pass the arguments literally
(`init=False`, not `init=SOME_FLAG`) — type checkers don't evaluate expressions.

## Sending, editing, answering

```python
screen = Counter(value=1)

screen.send(chat_id, message_thread_id=7)              # SendMessage
screen.edit(message=message)                           # EditMessageText
screen.edit(chat_id=chat_id, message_id=message_id)
screen.edit(inline_message_id=inline_message_id)
```

`send()` and `edit()` accept the usual Bot API options (`parse_mode`,
`link_preview_options`, `reply_parameters`, `business_connection_id`, …).
`edit(message=...)` takes the chat, message id and business connection from the
message.

```python
from aiogram_screens import CallbackQueryAnswerScreen


class Saved(CallbackQueryAnswerScreen):
    def create_text(self) -> str:
        return "Saved!"


await Saved().answer(query, show_alert=True)  # bound to the query's bot
await bot(Saved().answer(query.id))           # a plain method, send it explicitly
```

### Returned methods are not sent

Methods built by screens are not bound to a bot. Either return them from a
handler — the dispatcher sends them — or send them explicitly:

```python
await bot(screen.send(chat_id))
```

Only `answer(query)` returns a bound method, because it uses the query's own
shortcut.

## Replacer

`Replacer` updates the conversation after a user action: it builds the next
screen in place of the message the user interacted with, keeping its chat,
thread, direct messages topic and business connection.

```python
from aiogram_screens import Replacer


@router.callback_query(F.data.startswith("inc:"))
async def increment(query: CallbackQuery) -> TelegramMethod[Any] | None:
    value = int(query.data.removeprefix("inc:")) + 1
    if query.message is None:
        return None
    return await Replacer(Counter(value=value)).edit_or_replace(query.message)
```

| Method | What happens to the old message | New message |
|---|---|---|
| `replace(message)` | Deleted; if deleting fails, its keyboard is removed instead | Sent |
| `edit_or_replace(message)` | Edited in place if the screen is an `EditableMessageScreen` and the message is accessible; otherwise as `replace` | Sent only on fallback |
| `new(message)` | Its keyboard is removed | Sent; with `reply_parameters=NewReplyParameters(...)` it replies to the old message |

> [!IMPORTANT]
> The old message is deleted (or its keyboard removed) **immediately**, when you
> call the method; the new message is only built and is sent when the
> dispatcher handles the returned method. If sending fails, the user is left
> with neither message.

The deletion uses `safe_call`, so a failure is logged, not raised.

## `safe_call`

`safe_call` awaits a bound Telegram method and returns `(True, result)` on
success or `(False, None)` on a Telegram API error:

```python
from aiogram_screens import safe_call

ok, _ = await safe_call(message.delete())
if not ok:
    ...
```

API errors are logged as `WARNING` to the `aiogram_screens.safe` logger. Other
exceptions are re-raised; pass `raise_non_api_error=False` to log them as
`ERROR` instead. `log_level_resolver` overrides the level per exception.

## Development

The project is managed with [uv](https://docs.astral.sh/uv/); checks run with
[nox](https://nox.thea.codes/).

```sh
uv sync                    # create .venv with the linters and tests groups
uv run pytest              # quick test run on the pinned Python (3.11)

uvx nox                    # lint + tests on Python 3.11–3.14 + combined coverage
uvx nox -s format          # ruff check --fix + ruff format
uvx nox -s lint            # ruff check, ruff format --check, mypy --strict
uvx nox -s tests-3.14      # tests on one Python version
```

## License

MIT
