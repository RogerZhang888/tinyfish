from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parent / ".env")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

from backend.routes.recommendations import router as recommendation_router

app = FastAPI(
    title="RunWise API",
    version="0.1.0",
    description="Intelligent running shoe recommendations powered by TinyFish + LLM pipeline",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(recommendation_router)
