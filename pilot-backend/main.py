"""
PILOT Backend — entry point.
Wires up all agents, configures FastAPI, and starts uvicorn.
"""
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.actor import ActorAgent
from agents.orchestrator import Orchestrator
from agents.planner import PlannerAgent
from agents.verifier import VerifierAgent
from api.routes import router
from config import settings
from core.container import container
from core.groq_client import GroqLLMClient
from core.ollama_client import OllamaClient

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# Quiet down noisy third-party loggers
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("groq").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.groq_api_key == "MISSING_KEY":
        logger.warning(
            "GROQ_API_KEY is not set! Copy .env.example → .env and fill in your key."
        )

    groq = GroqLLMClient(api_key=settings.groq_api_key)

    ollama: OllamaClient | None = None
    if settings.ollama_enabled:
        ollama = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
        available = await ollama.is_available()
        logger.info(
            "Ollama at %s — %s",
            settings.ollama_base_url,
            "AVAILABLE" if available else "NOT reachable (will fall back to Groq only)",
        )
    else:
        logger.info("Ollama disabled")

    planner = PlannerAgent(groq=groq, ollama=ollama)
    actor = ActorAgent(groq=groq, ollama=ollama)
    verifier = VerifierAgent(groq=groq, ollama=ollama)
    orchestrator = Orchestrator(planner=planner, actor=actor, verifier=verifier)

    container.orchestrator = orchestrator

    logger.info("PILOT backend ready on http://%s:%d", settings.host, settings.port)
    logger.info(
        "Models → Planner: %s | Actor: %s | Verifier: %s | Vision: %s",
        settings.planner_model,
        settings.actor_model,
        settings.verifier_model,
        settings.vision_model,
    )

    yield

    # Shutdown
    logger.info("PILOT backend shutting down")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="PILOT Backend",
    description="Multi-agent AI system — voice-controlled phone automation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
