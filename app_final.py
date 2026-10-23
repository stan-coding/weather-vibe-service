"""Weather Vibe: погода, одежда и музыка для выбранного города."""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request

# ---------- Настройки ----------
load_dotenv()  # читает файл .env, если он есть; уже заданные через export переменные не перезаписывает

APP_NAME = os.getenv("APP_NAME", "Weather Vibe")
APP_VERSION = "0.4.1"
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
        raise WeatherServiceError(f"{url}: {error}") from error


def find_city(city: str) -> dict:
    """Найти координаты города по названию."""
    data = request_json(GEOCODING_URL, {"name": city, "count": 10, "language": "ru", "format": "json"})
    results = data.get("results")  # если ничего не найдено, ключа results в ответе нет
    if not results:
        raise CityNotFoundError(city)
    # Поиск идёт по началу названия и может вернуть несколько мест с похожими именами.
    # Берём самое крупное по населению: обычно это и есть нужный город.
    return max(results, key=lambda r: r.get("population") or 0)


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


# ---------- Рекомендации ----------
# Уровни по ощущаемой температуре: (верхняя граница °C, уровень, что надеть).
# Берётся первая строка, где ощущаемая температура меньше границы.
OUTFIT_LEVELS = [
    (-15, "очень холодно", ["пуховик", "термобельё", "тёплая шапка", "шарф", "варежки", "зимние ботинки"]),
    (-5, "холодно", ["зимняя куртка", "тёплый свитер", "шапка", "перчатки", "утеплённая обувь"]),
    (5, "прохладно", ["тёплая куртка или пальто", "свитер или худи", "шапка", "закрытая обувь"]),
    (12, "свежо", ["лёгкая куртка или ветровка", "кофта", "джинсы"]),
    (18, "комфортно", ["толстовка или кардиган", "футболка", "кроссовки"]),
    (25, "тепло", ["футболка", "лёгкие брюки или джинсы", "кеды"]),
    (float("inf"), "жарко", ["шорты или лёгкое платье", "одежда из хлопка или льна", "кепка или панама"]),
]

# Музыка по типу погоды: настроение и жанры.
MUSIC_BY_CATEGORY = {
    "clear": ("бодрое и солнечное", ["поп", "фанк", "инди-поп"]),
    "cloudy": ("спокойное", ["инди-рок", "соул", "альтернатива"]),
    "rain": ("уютное и задумчивое", ["лоу-фай", "джаз", "акустика"]),
    "snow": ("тихое и сказочное", ["эмбиент", "неоклассика", "классика"]),
    "fog": ("загадочное", ["трип-хоп", "эмбиент", "пост-рок"]),
    "storm": ("драматичное", ["рок", "саундтреки к фильмам", "симфоническая музыка"]),
}

STRONG_WIND_MS = 8  # с какой скорости ветра (м/с) советуем защиту от ветра


def outfit_advice(feels_like_c: float, category: str, wind_speed_ms: float = 0) -> dict:
    """Что надеть: по ощущаемой температуре, осадкам и ветру."""
    for upper, level, items in OUTFIT_LEVELS:
        if feels_like_c < upper:
            break

    extras = []
    if category in ("rain", "storm"):
        extras.append("зонт или дождевик и непромокаемая обувь")
    if category == "snow":
        extras.append("обувь с нескользящей подошвой")
    if category == "fog":
        extras.append("светлая одежда или светоотражатели, чтобы вас было видно")
    if category == "clear" and feels_like_c >= 18:
        extras.append("солнцезащитные очки и крем от загара")
    if wind_speed_ms >= STRONG_WIND_MS:
        extras.append("ветрозащитная куртка с капюшоном")
    if category == "storm":
        extras.append("по возможности переждите грозу в помещении")

    logger.debug("Одежда: %.1f°C, %s, ветер %.1f м/с -> %s", feels_like_c, category, wind_speed_ms, level)
    return {"level": level, "items": list(items), "extras": extras}


def music_advice(category: str, feels_like_c: float) -> dict:
    """Какую музыку послушать: по типу погоды, с поправкой на жару и мороз."""
    mood, genres = MUSIC_BY_CATEGORY.get(category, MUSIC_BY_CATEGORY["cloudy"])
    genres = list(genres)  # копия, чтобы не менять общий словарь
    if feels_like_c >= 25:
        genres.append("регги")
    elif feels_like_c < -10:
        genres.append("тёплый соул")

    logger.debug("Музыка: %s, %.1f°C -> %s", category, feels_like_c, genres)
    return {"mood": mood, "genres": genres}


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


# Параметр города: один раз описываем правила, используем во всех маршрутах
City = Annotated[
    str,
    Query(min_length=2, max_length=80, description="Город, например Penza или Москва"),
]


@app.get("/weather")
def weather(city: City = DEFAULT_CITY):
    """Текущая погода в городе."""
    return load_weather(city)


@app.get("/outfit")
def outfit(city: City = DEFAULT_CITY):
    """Что надеть по текущей погоде."""
    w = load_weather(city)
    return {
        "city": w["city"],
        "feels_like_c": w["feels_like_c"],
        "description": w["description"],
        "outfit": outfit_advice(w["feels_like_c"], w["category"], w["wind_speed_ms"]),
    }


@app.get("/music")
def music(city: City = DEFAULT_CITY):
    """Какую музыку послушать по текущей погоде."""
    w = load_weather(city)
    return {
        "city": w["city"],
        "description": w["description"],
        "music": music_advice(w["category"], w["feels_like_c"]),
    }


@app.get("/vibe")
def vibe(city: City = DEFAULT_CITY):
    """Всё сразу: погода, одежда и музыка."""
    w = load_weather(city)
    return {
        "weather": w,
        "outfit": outfit_advice(w["feels_like_c"], w["category"], w["wind_speed_ms"]),
        "music": music_advice(w["category"], w["feels_like_c"]),
    }