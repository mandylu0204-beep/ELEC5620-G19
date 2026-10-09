from collections.abc import Callable

from ..agents.stub import StubAgent
from ..contracts.enums import ExecutionMode
from ..contracts.ports import AgentPort

# B registers its factory here. Missing modes remain unavailable, never fall back to stub.
AGENT_FACTORIES: dict[ExecutionMode, Callable[[], AgentPort]] = {
    ExecutionMode.STUB: StubAgent,
}


def create_agent(mode: ExecutionMode) -> AgentPort | None:
    factory = AGENT_FACTORIES.get(mode)
    return factory() if factory is not None else None
