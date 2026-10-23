"""Weather Vibe: погода, одежда и музыка для выбранного города."""

import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request

# ---------- Настройки ----------
load_dotenv()  # читает файл .env, если он есть; уже заданные через export переменные не перезаписывает

APP_NAME = os.getenv("APP_NAME", "Weather Vibe")
APP_VERSION = "0.3.0"
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Penza")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "5"))  # сколько секунд ждать ответа от сервиса погоды

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ---------- Логи ----------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("weather_vibe")

# ---------- Коды погоды WMO: код -> (описание, категория) ----------
WEATHER_CODES = {
    0: ("ясно", "clear"),
    1: ("преимущественно ясно", "clear"),
    2: ("переменная облачность", "cloudy"),
    3: ("пасмурно", "cloudy"),
    45: ("туман", "fog"),
    48: ("туман с изморозью", "fog"),
    51: ("слабая морось", "rain"),
    53: ("морось", "rain"),
    55: ("сильная морось", "rain"),
    56: ("слабая ледяная морось", "rain"),
    57: ("сильная ледяная морось", "rain"),
    61: ("небольшой дождь", "rain"),
    63: ("дождь", "rain"),
    65: ("сильный дождь", "rain"),
    66: ("слабый ледяной дождь", "rain"),
    67: ("сильный ледяной дождь", "rain"),
    71: ("небольшой снег", "snow"),
    73: ("снег", "snow"),
    75: ("сильный снег", "snow"),
    77: ("снежная крупа", "snow"),
    80: ("небольшой ливень", "rain"),
    81: ("ливень", "rain"),
    82: ("сильный ливень", "rain"),
    85: ("небольшой снегопад", "snow"),
    86: ("сильный снегопад", "snow"),
    95: ("гроза", "storm"),
    96: ("гроза с небольшим градом", "storm"),
    97: ("сильная гроза", "storm"),
    99: ("гроза с сильным градом", "storm"),
}


def describe_weather(code: int) -> tuple[str, str]:
    """Перевести числовой код погоды в описание и категорию."""
    return WEATHER_CODES.get(code, ("неизвестно", "cloudy"))


# ---------- Работа с Open-Meteo ----------
class CityNotFoundError(Exception):
    """Город не найден в справочнике."""


class WeatherServiceError(Exception):
    """Сервис погоды не ответил или ответил с ошибкой."""


def request_json(url: str, params: dict) -> dict:
    """GET-запрос к внешнему сервису; любая сетевая ошибка превращается в WeatherServiceError."""
    try:
        response = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # если сервис вернул 4xx/5xx — считаем это ошибкой
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise WeatherServiceError(str(error)) from error


def find_city(city: str) -> dict:
    """Найти координаты города по названию."""
    data = request_json(GEOCODING_URL, {"name": city, "count": 1, "language": "ru", "format": "json"})
    results = data.get("results")  # если ничего не найдено, ключа results в ответе нет
    if not results:
        raise CityNotFoundError(city)
    return results[0]


def get_weather(city: str) -> dict:
    """Текущая погода для города в удобном виде."""
    place = find_city(city)
    data = request_json(
        FORECAST_URL,
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "wind_speed_unit": "ms",
            "timezone": "auto",
        },
    )
    try:
        current = data["current"]
        description, category = describe_weather(current["weather_code"])
        weather = {
            "city": place.get("name", city),
            "country": place.get("country", ""),
            "observed_at": current["time"],
            "temperature_c": current["temperature_2m"],
            "feels_like_c": current["apparent_temperature"],
            "humidity_pct": current["relative_humidity_2m"],
            "wind_speed_ms": current["wind_speed_10m"],
            "weather_code": current["weather_code"],
            "description": description,
            "category": category,
        }
    except KeyError as error:
        raise WeatherServiceError(f"неожиданный формат ответа: нет поля {error}") from error

    logger.info(
        "Погода для %s: %.1f°C (ощущается %.1f°C), %s",
        weather["city"], weather["temperature_c"], weather["feels_like_c"], description,
    )
    return weather


def load_weather(city: str) -> dict:
    """Получить погоду или вернуть клиенту понятную HTTP-ошибку."""
    try:
        return get_weather(city)
    except CityNotFoundError:
        logger.warning("Город не найден: %s", city)
        raise HTTPException(status_code=404, detail=f"Город '{city}' не найден")
    except WeatherServiceError as error:
        logger.error("Сервис погоды недоступен: %s", error)
        raise HTTPException(status_code=503, detail="Сервис погоды временно недоступен, попробуйте позже")


# ---------- Приложение ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # код до yield выполняется при запуске сервера, после yield — при остановке
    logger.info("Запуск %s v%s, город по умолчанию: %s", APP_NAME, APP_VERSION, DEFAULT_CITY)
    yield
    logger.info("Остановка %s", APP_NAME)


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # срабатывает на каждый запрос: засекаем время, передаём запрос дальше, пишем итог в лог
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


@app.get("/weather")
def weather(
    city: str = Query(DEFAULT_CITY, min_length=2, max_length=80, description="Город, например Penza или Москва"),
):
    """Текущая погода в городе."""
    return load_weather(city)
