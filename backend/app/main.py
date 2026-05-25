from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import connect_db, disconnect_db
from app.core.redis import connect_redis, disconnect_redis
from app.core.logging import setup_logging, logger

from app.routers import webhook, incidents, auth, chat, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    await connect_db()
    await connect_redis()
    logger.info("startup_complete", env=settings.APP_ENV)
    yield
    # Shutdown
    await disconnect_db()
    await disconnect_redis()
    logger.info("shutdown_complete")


app = FastAPI(
    title="DevOps AI Copilot",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(webhook.router, tags=["webhook"])
app.include_router(incidents.router, tags=["incidents"])
app.include_router(auth.router, tags=["auth"])
app.include_router(chat.router, tags=["chat"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}