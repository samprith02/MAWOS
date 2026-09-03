"""Base class for all MAWOS agents.

An agent = a named unit with a goal, its own logic, the ability to read/write
the shared context store, and pub/sub communication with other agents.
Deterministic by default; only the Orchestrator touches the (optional) LLM.
"""
from ..bus import EventBus
from ..database import SessionLocal


class BaseAgent:
    name: str = "base"
    description: str = ""

    def __init__(self, bus: EventBus):
        self.bus = bus
        self.register_subscriptions()

    def register_subscriptions(self) -> None:
        """Override to wire bus.subscribe(topic, self.name, handler)."""

    def session(self):
        return SessionLocal()

    async def publish(self, topic: str, payload: dict) -> str:
        return await self.bus.publish(topic, payload, source_agent=self.name)

    async def answer_query(self, db, user, query: str) -> dict:
        """Chat-path entry point; override in queryable agents."""
        return {"agent": self.name, "text": "This agent does not handle chat queries."}
