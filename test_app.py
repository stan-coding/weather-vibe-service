"""Автотесты Weather Vibe. Интернет не нужен: запросы к Open-Meteo подменяются заглушкой."""

import pytest
from fastapi.testclient import TestClient

import app_final
from app_final import app, music_advice, outfit_advice

client = TestClient(app)

# ---------- Тестовые данные вместо ответов Open-Meteo ----------
PENZA = {"name": "Пенза", "country": "Россия", "latitude": 53.2, "longitude": 45.0, "population": 500000}
PENZA_ZAMBIA = {"name": "Penza", "country": "Замбия", "latitude": -14.2, "longitude": 28.6, "population": 0}
SNOWY_WEATHER = {
    "time": "2026-10-23T12:00",
    "temperature_2m": -3.0,
    "apparent_temperature": -8.0,
    "relative_humidity_2m": 80,
    "wind_speed_10m": 9.0,
    "weather_code": 73,  # снег
}


def fake_open_meteo(places):
    """Создать подмену для request_json: вернёт заданные города и снежную погоду."""
    def fake_request_json(url, params):
        if url == app_final.GEOCODING_URL:
            return {"results": places} if places else {}
        return {"current": SNOWY_WEATHER}
    return fake_request_json


@pytest.fixture
def fake_api(monkeypatch):
    """Подменить запросы в интернет: Open-Meteo «находит» Пензу."""
    monkeypatch.setattr(app_final, "request_json", fake_open_meteo([PENZA]))


# ---------- Служебные маршруты ----------
def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json()["version"] == app_final.APP_VERSION


# ---------- Погода и рекомендации ----------
def test_weather_returns_data(fake_api):
    response = client.get("/weather", params={"city": "Penza"})
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Пенза"
    assert data["temperature_c"] == -3.0
    assert data["description"] == "снег"
    assert data["category"] == "snow"


def test_vibe_gives_outfit_and_music(fake_api):
    response = client.get("/vibe", params={"city": "Penza"})
    assert response.status_code == 200
    data = response.json()
    assert data["outfit"]["level"] == "холодно"  # ощущается как -8°C
    assert "обувь с нескользящей подошвой" in data["outfit"]["extras"]
    assert data["music"]["mood"] == "тихое и сказочное"


def test_most_populous_city_is_chosen(monkeypatch):
    # Ошибка, найденная при ручной проверке: посёлок Penza в Замбии побеждал Пензу в России
    monkeypatch.setattr(app_final, "request_json", fake_open_meteo([PENZA_ZAMBIA, PENZA]))
    response = client.get("/weather", params={"city": "Penza"})
    assert response.status_code == 200
    assert response.json()["country"] == "Россия"


# ---------- Ошибки ----------
def test_city_not_found(monkeypatch):
    monkeypatch.setattr(app_final, "request_json", fake_open_meteo([]))
    response = client.get("/weather", params={"city": "Qwxyzabc"})
    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


def test_weather_service_unavailable(monkeypatch):
    def broken_request_json(url, params):
        raise app_final.WeatherServiceError("timed out")

    monkeypatch.setattr(app_final, "request_json", broken_request_json)
    response = client.get("/weather", params={"city": "Penza"})
    assert response.status_code == 503


def test_city_name_too_short():
    response = client.get("/weather", params={"city": "a"})
    assert response.status_code == 422


# ---------- Ручной режим ----------
def test_advice_manual_mode():
    response = client.get("/advice", params={"temp": -20, "category": "snow", "wind": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["outfit"]["level"] == "очень холодно"
    assert "ветрозащитная куртка с капюшоном" in data["outfit"]["extras"]
    assert "тёплый соул" in data["music"]["genres"]


def test_advice_rejects_unknown_category():
    response = client.get("/advice", params={"temp": 20, "category": "tornado"})
    assert response.status_code == 422


# ---------- Функции рекомендаций (без HTTP) ----------
@pytest.mark.parametrize(
    "feels_like, expected_level",
    [
        (-30, "очень холодно"),
        (-10, "холодно"),
        (0, "прохладно"),
        (10, "свежо"),
        (15, "комфортно"),
        (20, "тепло"),
        (30, "жарко"),
    ],
)
def test_outfit_levels(feels_like, expected_level):
    assert outfit_advice(feels_like, "cloudy")["level"] == expected_level


def test_music_advice_does_not_change_shared_dict():
    before = list(app_final.MUSIC_BY_CATEGORY["clear"][1])
    music_advice("clear", 30)  # в ответ добавится «регги»
    assert app_final.MUSIC_BY_CATEGORY["clear"][1] == before