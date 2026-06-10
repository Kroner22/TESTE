from __future__ import annotations

import time
from typing import Callable, Optional

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from .rate_limit import get_rate_limiter
from ..log_config import get_logger
from ..plan_limiter import get_plan_limit, PLAN_LIMITS

logger = get_logger(__name__)

JWT_SECRET = "omega-predictions-jwt-secret-change-in-production"
JWT_ALGORITHM = "HS256"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._should_rate_limit(request):
            return await call_next(request)

        identifier = self._resolve_identifier(request)
        plan = self._resolve_plan(request)
        route = request.url.path
        limiter = get_rate_limiter()

        max_requests = get_plan_limit(plan)
        allowed, current, wait = limiter.check(identifier, route, max_requests=max_requests)
        if not allowed:
            logger.warning("rate_limit_exceeded", identifier=identifier, route=route, plan=plan)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": f"Muitas requisicoes. Limite: {max_requests}/min. Tente novamente em {wait:.1f}s",
                    "retry_after_seconds": round(wait, 1),
                    "plan": plan,
                    "limit": max_requests,
                },
                headers={
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(int(wait)),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, current))
        response.headers["X-RateLimit-Plan"] = plan
        return response

    def _should_rate_limit(self, request: Request) -> bool:
        path = request.url.path
        if path.startswith("/metrics") or path.startswith("/health"):
            return False
        return True

    def _resolve_identifier(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _resolve_plan(self, request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return "free"
        token = auth[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get("plan", "free")
        except JWTError:
            return "free"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.monotonic()
        body = None

        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.json()
            except Exception:
                body = None

        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 1),
            content_length=response.headers.get("content-length"),
            client_host=request.client.host if request.client else None,
        )

        response.headers["X-Request-Time-Ms"] = str(round(elapsed_ms, 1))
        return response
