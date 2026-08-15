"""MAWOS v2 — event-driven multi-agent workflow orchestration for a full
institution. Single process: agents + bus + context store + web portals."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, llm
from . import router as hybrid_router
from .agents import get_agents
from .api.routes import router
from .database import Base, SessionLocal, engine
from .models import TimetableSlot
from .seed import bootstrap_evaluations, seed_all

PROACTIVE_INTERVAL_S = 300  # agents run their own scans every 5 minutes


async def _proactive_loop(agents):
    while True:
        await asyncio.sleep(PROACTIVE_INTERVAL_S)
        try:
            await agents["attendance_agent"].proactive_scan()
            await agents["finance_agent"].proactive_scan()
        except Exception as exc:  # keep the loop alive
            print(f"[MAWOS] proactive scan error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    freshly_seeded = seed_all()
    agents = get_agents()
    if freshly_seeded:
        print("[MAWOS] fresh seed — bootstrapping evaluations…")
        bootstrap_evaluations(agents)
    db = SessionLocal()
    try:
        if db.query(TimetableSlot).count() == 0:
            print("[MAWOS] generating institution timetable…")
            result = agents["timetable_agent"].generate(db)
            print(f"[MAWOS] timetable: {result['slots_placed']} slots, "
                  f"{result['placement_rate']}% placed, "
                  f"{result['solve_ms']} ms")
    finally:
        db.close()
    mode = (f"hybrid router, tau {hybrid_router.TAU:.2f}, escalating to "
            f"{config.OLLAMA_MODEL}") if llm.check_ollama() else \
        "lexicon only (install Ollama + qwen2.5 to enable escalation)"
    print(f"[MAWOS] {len(agents)} agents online · AI mode: {mode}")
    task = asyncio.create_task(_proactive_loop(agents))
    yield
    task.cancel()


app = FastAPI(title="MAWOS", version="2.0.0", lifespan=lifespan)
app.include_router(router)

if config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(config.STATIC_DIR / "index.html"))
