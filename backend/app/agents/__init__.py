"""Agent registry.

R1 (docs/v4/04_DATA_MODEL.md §4.4): `AdmissionAgent` is **removed** with the
admissions module -- 400 records, a 4-stage batch pipeline and zero agent
interaction (`docs/v4/02_SCOPE.md` DO-NOT-BUILD). Its only chat-facing tool
was already retired at v3's P2.

The v4 target agent set and the three-clause criterion that produces it are
in `docs/v4/01_ARCHITECTURE.md` §3. That refactor is **R3**, not R1;
CORE_AGENTS below still names the v3 four, and the remaining entries are
still tool-backed components or bus subscribers, not agents.
"""
from ..bus import bus
from .academic import AcademicAgent
from .attendance import AttendanceAgent
from .eligibility import EligibilityAgent
from .finance import FinanceAgent
from .notification import NotificationAgent
from .orchestrator import OrchestratorAgent
from .placement import PlacementAgent
from .timetable import TimetableAgent

#: The four that meet the pre-registered agent criterion (plan §7).
#: Everything else in the registry is a tool-backed component or (for
#: notification_agent) a bus subscriber that is not counted as an agent.
CORE_AGENTS = ("orchestrator_agent", "attendance_agent",
               "eligibility_agent", "timetable_agent")

_agents: dict | None = None


def get_agents() -> dict:
    global _agents
    if _agents is None:
        registry = {}
        for cls in (TimetableAgent, AcademicAgent,
                    AttendanceAgent, FinanceAgent, EligibilityAgent,
                    PlacementAgent, NotificationAgent):
            agent = cls(bus)
            registry[agent.name] = agent
        registry["orchestrator_agent"] = OrchestratorAgent(bus, registry)
        _agents = registry
    return _agents
