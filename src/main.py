from fastapi import FastAPI
from src.api.v1 import execute, jobs, stream, terminal


app = FastAPI(title="safe-god-mode")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(execute.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(terminal.router, prefix="/api/v1")
