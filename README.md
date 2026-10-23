# Weather Vibe

[![Weather Vibe CI](https://github.com/stan-coding/weather-vibe-service/actions/workflows/ci.yml/badge.svg)](https://github.com/stan-coding/weather-vibe-service/actions/workflows/ci.yml)

Небольшой сервис на FastAPI: по названию города показывает текущую погоду, советует, как одеться, и какую музыку послушать под эту погоду.

**Для кого:** для тех, кто перед выходом из дома хочет за один запрос понять, что надеть и что включить в наушниках. Проект сделан как итоговая работа по курсу «Инфраструктура и администрирование» и показывает полный путь сервиса: код → Git → тесты → CI → запуск и диагностика.

Данные о погоде: [Open-Meteo.com](https://open-meteo.com/) (бесплатно, без ключа API, лицензия CC BY 4.0).

## Маршруты

| Адрес | Что возвращает |
|---|---|
| `GET /` | Сообщение, что сервис работает |
| `GET /health` | Техническая проверка: `{"status": "ok"}` |
| `GET /version` | Название и версия приложения |
| `GET /weather?city=Penza` | Текущая погода: температура, ощущается как, влажность, ветер, описание |
| `GET /outfit?city=Penza` | Что надеть по текущей погоде |
| `GET /music?city=Penza` | Какую музыку послушать: настроение и жанры |
| `GET /vibe?city=Penza` | Всё сразу: погода, одежда и музыка |
| `GET /advice?temp=-20&category=snow&wind=10` | Ручной режим: советы по заданной погоде, без запроса в интернет |

Если `city` не указан, берётся город из настройки `DEFAULT_CITY`.

Параметры `/advice`:
- `temp` (обязательный): ощущаемая температура, от −60 до 60 °C;
- `category`: тип погоды `clear`, `cloudy`, `rain`, `snow`, `fog` или `storm` (по умолчанию `clear`);
- `wind`: скорость ветра, м/с (по умолчанию 0).

Пример ответа `/vibe`:

```json
{
  "weather": {"city": "Пенза", "country": "Россия", "temperature_c": 14.0, "feels_like_c": 10.7,
              "humidity_pct": 41, "wind_speed_ms": 2.37, "description": "переменная облачность", "category": "cloudy"},
  "outfit": {"level": "свежо", "items": ["лёгкая куртка или ветровка", "кофта", "джинсы"], "extras": []},
  "music": {"mood": "спокойное", "genres": ["инди-рок", "соул", "альтернатива"]}
}
```

## Как работает

1. По названию города сервис находит координаты через Geocoding API Open-Meteo. Если найдено несколько мест, выбирается самое крупное по населению.
2. По координатам получает текущую погоду через Forecast API.
3. Числовой код погоды (WMO) переводится в описание и категорию: ясно, облачно, дождь, снег, туман, гроза.
4. Одежда подбирается по **ощущаемой** температуре (7 уровней от «очень холодно» до «жарко») с добавками: зонт при дожде, нескользящая обувь при снеге, защита от ветра от 8 м/с.
5. Музыка подбирается по категории погоды, с поправкой на жару и мороз.

## Установка

Нужны Linux, macOS или Windows с WSL, Python 3.11+ (проверено на 3.12) и Git.

```bash
git clone https://github.com/stan-coding/weather-vibe-service.git
cd weather-vibe-service
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

## Переменные окружения

Настройки читаются из переменных окружения или из файла `.env` (шаблон: `.env.example`). Переменная, заданная через `export`, важнее значения в `.env`.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APP_NAME` | `Weather Vibe` | Название сервиса в `/`, `/version` и логах |
| `DEFAULT_CITY` | `Penza` | Город, если в запросе не указан `city` |
| `LOG_LEVEL` | `INFO` | Подробность логов: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `REQUEST_TIMEOUT` | `5` | Сколько секунд ждать ответа от Open-Meteo |

Файл `.env` не хранится в Git. Секретов у проекта нет: Open-Meteo не требует ключа.

## Запуск

Для разработки (перезапуск при изменении кода):

```bash
python -m uvicorn app_final:app --reload
```

Для обычной работы, без `--reload`:

```bash
python -m uvicorn app_final:app --host 127.0.0.1 --port 8000
```

После запуска:
- приложение: http://127.0.0.1:8000
- документация и форма для запросов: http://127.0.0.1:8000/docs

Остановить сервер: `Ctrl+C`.

## Проверка

Во втором терминале:

```bash
curl http://127.0.0.1:8000/health      # {"status":"ok"}
curl http://127.0.0.1:8000/version     # {"app":"Weather Vibe","version":"1.0.0"}
curl -s "http://127.0.0.1:8000/vibe?city=London" | python -m json.tool --no-ensure-ascii
curl -s "http://127.0.0.1:8000/advice?temp=-20&category=snow" | python -m json.tool --no-ensure-ascii
curl -s -G --data-urlencode "city=Москва" http://127.0.0.1:8000/weather   # город кириллицей
```

## Логи

Логи выводятся в терминал, где запущен сервер. Формат: время, уровень, источник, сообщение.

```text
2026-10-23 13:34:28,469 INFO weather_vibe: Запуск Weather Vibe v1.0.0, город по умолчанию: Penza
2026-10-23 13:34:36,787 INFO weather_vibe: Погода для Пенза: 14.0°C (ощущается 10.7°C), переменная облачность
2026-10-23 13:34:36,788 INFO weather_vibe: GET /vibe -> 200 (2498 ms)
2026-10-23 13:09:12,184 WARNING weather_vibe: Город не найден: Qwxyzabc
2026-10-23 12:55:04,101 ERROR weather_vibe: Сервис погоды недоступен: https://api.open-meteo.com/v1/forecast: timed out
```

Что пишется в лог:
- запуск и остановка сервиса;
- каждый запрос: метод, адрес, код ответа и время обработки;
- найденная погода (`INFO`), ненайденный город (`WARNING`), недоступность Open-Meteo (`ERROR`);
- при `LOG_LEVEL=DEBUG` ещё и детали подбора одежды и музыки.

Сохранить логи в файл и найти ошибки:

```bash
python -m uvicorn app_final:app 2>&1 | tee app.log
grep -E "WARNING|ERROR" app.log
```

Подробный режим на один запуск:

```bash
LOG_LEVEL=DEBUG python -m uvicorn app_final:app
```

## Тесты

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -v
```

18 тестов проверяют `/health`, `/version`, погоду, рекомендации, ручной режим и ошибки (404, 422, 503). Интернет для тестов не нужен: запросы к Open-Meteo подменяются заглушкой (`monkeypatch`), поэтому результат не зависит от погоды и доступности внешнего сервиса.

## CI

Workflow `.github/workflows/ci.yml` запускается при push и pull request в `main` (и вручную кнопкой **Run workflow**):

1. job `test`: чистая Ubuntu, Python 3.12, установка зависимостей, `python -m pytest -v`;
2. job `package`: запускается только после успешных тестов и создаёт artifact `weather-vibe-service` (`app_final.py`, `requirements.txt`, `.env.example`, `README.md`), который хранится 30 дней.

Результаты: вкладка [Actions](https://github.com/stan-coding/weather-vibe-service/actions).

## Диагностика

Порядок проверки, если сервис не отвечает:
1. Запущен ли процесс? Смотри терминал с uvicorn.
2. Какой адрес и порт он слушает? `ss -ltnp | grep 8000`
3. Отвечает ли он на этом компьютере? `curl http://127.0.0.1:8000/health`
4. Что написано в логе в момент запроса?

| Симптом | Причина | Что сделать |
|---|---|---|
| `Address already in use` | Порт 8000 занят, например вторым uvicorn | Остановить прежний сервер (`Ctrl+C`) или запустить с `--port 8001` |
| `curl: Connection refused` | Сервер не запущен или другой порт | Проверить терминал с uvicorn и порт |
| `No module named fastapi` / `httpx` | Не активировано окружение или не установлены зависимости | `source .venv/bin/activate`, затем `python -m pip install -r requirements.txt` |
| `python: command not found` | Окружение не активировано (в Ubuntu есть только `python3`) | `source .venv/bin/activate` |
| Ответ **503**, в логе `ERROR ... Сервис погоды недоступен: <адрес>: timed out` | Open-Meteo не ответил вовремя: нет сети, медленный прокси или VPN | Проверить доступ: `curl -sS -m 10 -o /dev/null -w "%{http_code}\n" "https://api.open-meteo.com/v1/forecast?latitude=53.2&longitude=45&current=temperature_2m"`. Повторить запрос или увеличить `REQUEST_TIMEOUT` в `.env` |
| В логе `handshake operation timed out` | То же: шифрованное соединение не установилось вовремя, часто из-за прокси | Как в строке выше. В WSL может помочь `networkingMode=mirrored` в `%USERPROFILE%\.wslconfig` |
| Ответ **404** «Город не найден» | Опечатка или город отсутствует в справочнике | Проверить название, попробовать латиницей |
| Ответ **422** | Неверный параметр: город короче 2 символов, `temp` вне диапазона, неизвестная `category` | В ответе поле `detail` указывает, какой параметр неверен |
| Изменения в `.env` не применились | `.env` читается только при запуске; `--reload` следит лишь за `.py` | Перезапустить сервер |
| curl к `127.0.0.1` идёт через прокси (в ответе `Proxy-Connection`) | В системе задан `HTTP(S)_PROXY` | `curl --noproxy 127.0.0.1 ...` |
| Красный запуск в Actions | Упал тест | `gh run view --log-failed`, найти строку `FAILED` и `AssertionError` |

Пример разбора красного CI ([запуск](https://github.com/stan-coding/weather-vibe-service/actions/runs/40018434296)): ответ `/health` намеренно изменили на `broken`. В логе:

```text
E       AssertionError: assert {'status': 'broken'} == {'status': 'ok'}
FAILED test_app.py::test_health
```

Видно, какой тест упал, что ожидалось и что пришло. Job `package` не запустился, то есть сломанная версия не была упакована. Следующий коммит `Restore health contract` вернул зелёный статус.

## Известные ограничения

- Поиск городов Open-Meteo ищет по началу названия, и для части городов кириллица находит не то место. Например, «Мурманск» находит посёлок «Мурманский» в другом регионе (это видно по часовому поясу и погоде). Латиницей (`Murmansk`) город находится верно.
- Рекомендации построены на простых правилах, а не на машинном обучении.
- Погода только текущая, без прогноза.

## Структура проекта

```text
weather-vibe-service/
├── app_final.py              # приложение FastAPI
├── test_app.py               # автотесты
├── requirements.txt          # зависимости для работы
├── requirements-dev.txt      # зависимости для тестов
├── .env.example              # шаблон настроек
├── .gitignore
├── .gitattributes            # переносы строк LF
├── README.md
└── .github/workflows/ci.yml  # CI в GitHub Actions
```

## Источник и доработки

Основа: учебный пример курса [maximblaze/test_project_inf_course](https://github.com/maximblaze/test_project_inf_course) (`app_final.py`, `test_app.py`, `ci.yml`).

Что сделано сверх примера:
- своя тема: погода, одежда и музыка; работа с внешним API Open-Meteo;
- 5 тематических маршрутов с параметрами и проверкой входных данных;
- обработка ошибок внешнего сервиса (404, 503) и таймаут из настроек;
- настройки через переменные окружения и `.env`;
- логирование запуска, запросов, результатов и ошибок;
- ручной режим `/advice` без интернета;
- 18 собственных тестов с подменой внешнего API;
- CI с artifact и разобранным примером красного запуска.

## Паспорт проекта

| Поле | Значение |
|---|---|
| Git repository | https://github.com/stan-coding/weather-vibe-service |
| Application port | 8000 |
| Local URL | http://127.0.0.1:8000 |
| Health check | `curl http://127.0.0.1:8000/health` |
| Workflow | `.github/workflows/ci.yml` |
| Artifact | `weather-vibe-service` |
| Автор | Stanislav Eremin |
