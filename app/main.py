from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .database import Base, SessionLocal, engine
from .realtime import manager
from .routers import account, admin, auth, community, dashboard, events, projects, public, questions
from .security import decode_access_token
from .seed import seed_database

logger = logging.getLogger("campus_innovators")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Local/dev convenience. Production deployments should run `alembic upgrade head` before startup.
    if not settings.is_production:
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="3.0.0",
    description="Campus Innovators student community API with public dashboards, profiles, JWT access tokens and rotating refresh sessions.",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


for router in [public.router, auth.router, dashboard.router, community.router, questions.router, projects.router, events.router, account.router, admin.router]:
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "status": "ok", "version": "3.0.0"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    offered = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",") if item.strip()]
    token_protocol = next((item for item in offered if item.startswith("jwt.")), None)
    if token_protocol is None:
        await websocket.close(code=1008)
        return
    try:
        user_id = decode_access_token(token_protocol[4:])
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket, subprotocol="campus-v1" if "campus-v1" in offered else None)
    try:
        await websocket.send_json({"type": "connected", "message": "Live campus updates connected."})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
