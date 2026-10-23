"""Weather Vibe: погода, одежда и музыка для выбранного города."""

import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request

# ---------- Настройки ----------
load_dotenv()
APP_NAME = os.getenv("APP_NAME", "Weather Vibe")
APP_VERSION = "0.2.0"
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Penza")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------- Логи ----------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("weather_vibe")


@asynccontextmanager
async def lifespan(app: FastAPI):
    
    logger.info("Запуск %s v%s, город по умолчанию: %s", APP_NAME, APP_VERSION, DEFAULT_CITY)
    yield
    logger.info("Остановка %s", APP_NAME)


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.0f ms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


@app.get("/")
def root():
    return {"message": "Сервис работает", "service": APP_NAME}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"app": APP_NAME, "version": APP_VERSION}