from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.schemas.agent import AgentConfig


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    payload: dict[str, Any]


class VoiceRuntime(ABC):
    @abstractmethod
    async def validate_environment(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def run_test_call(
        self, config: AgentConfig, session_id: str
    ) -> AsyncIterator[RuntimeEvent]:
        raise NotImplementedError
