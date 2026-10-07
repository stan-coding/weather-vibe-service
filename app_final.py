"""Weather Vibe: погода, одежда и музыка для выбранного города."""

from fastapi import FastAPI

app = FastAPI(title="Weather Vibe")


@app.get("/")
def root():
    return {"message": "Сервис работает"}


@app.get("/health")
def health():
    return {"status": "ok"}
