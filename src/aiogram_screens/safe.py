from collections.abc import Callable
from logging import ERROR, WARNING, getLogger
from typing import Literal, TypeAlias, TypeVar

from aiogram.exceptions import TelegramAPIError
from aiogram.methods import TelegramMethod

LogLevelResolver: TypeAlias = Callable[[Exception], int]
_T = TypeVar("_T")


logger = getLogger(__name__)


def _resolve_log_level(error: Exception) -> int:
    if isinstance(error, TelegramAPIError):
        return WARNING
    return ERROR


async def safe_call(
    method: TelegramMethod[_T],
    *,
    raise_non_api_error: bool = True,
    log_level_resolver: LogLevelResolver = _resolve_log_level,
) -> tuple[Literal[True], _T] | tuple[Literal[False], None]:
    try:
        return True, (await method)
    except TelegramAPIError as error:
        logger.log(log_level_resolver(error), repr(error), exc_info=error)
    except Exception as error:
        if raise_non_api_error:
            raise
        logger.log(log_level_resolver(error), repr(error), exc_info=error)
    return False, None
