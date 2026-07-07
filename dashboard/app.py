"""FastAPI entry for the vault dashboard."""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.api.routes import router

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Vault Dashboard", version="0.1.0")
app.include_router(router)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/explorer")
def explorer_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "explorer.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", "8787"))
    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
