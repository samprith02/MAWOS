"""Agent registry v2 — 10 agents wired to the instrumented bus."""
from ..bus import bus
from .academic import AcademicAgent
from .admission import AdmissionAgent
from .attendance import AttendanceAgent
from .exam import ExamAgent
from .finance import FinanceAgent
from .notification import NotificationAgent
from .orchestrator import OrchestratorAgent
from .placement import PlacementAgent
from .scholarship import ScholarshipAgent
from .timetable import TimetableAgent

_agents: dict | None = None


def get_agents() -> dict:
    global _agents
    if _agents is None:
        registry = {}
        for cls in (AdmissionAgent, TimetableAgent, AcademicAgent,
                    AttendanceAgent, FinanceAgent, ExamAgent,
                    ScholarshipAgent, PlacementAgent, NotificationAgent):
            agent = cls(bus)
            registry[agent.name] = agent
        registry["orchestrator_agent"] = OrchestratorAgent(bus, registry)
        _agents = registry
    return _agents
