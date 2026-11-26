from dataclasses import KW_ONLY, dataclass


@dataclass(frozen=True, slots=True)
class Widget:
    html: str
    _: KW_ONLY
    width: int | None = None
    height: int | None = None
    allow_queries: bool | None = None
