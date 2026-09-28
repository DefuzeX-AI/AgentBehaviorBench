from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Self

    from langchain_core.messages import BaseMessage


logger = logging.getLogger(__name__)


class AbstractEvaluatee(AbstractAsyncContextManager, ABC):
    @abstractmethod
    async def _call(self, message: BaseMessage, **kwargs) -> list[BaseMessage]: ...

    async def __call__(self, message: BaseMessage, **kwargs) -> list[BaseMessage]:
        # TODO: add callback to handle errors or other events
        return await self._call(message, **kwargs)

    @property
    def context(self):
        return {}

    @classmethod
    @abstractmethod
    def instance(cls) -> Self: ...
