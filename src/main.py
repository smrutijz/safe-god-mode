from fastapi import FastAPI

from src.api.v1.router import api_router

app = FastAPI(title="safe-god-mode")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(api_router, prefix="/api/v1")
