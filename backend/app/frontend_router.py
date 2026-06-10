from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

router = APIRouter(tags=["frontend"])


@router.get("/app", response_class=HTMLResponse)
async def serve_app(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/app/{path:path}", response_class=HTMLResponse)
async def serve_app_path(request: Request, path: str):
    return templates.TemplateResponse("index.html", {"request": request})
