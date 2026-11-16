"""Shared request controls for endpoints that invoke a language model."""

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from auth import get_current_user


def enforce_llm_rate_limit(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    limiter = getattr(request.app.state, "llm_rate_limiter", None)
    if limiter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El control de capacidad del modelo no está disponible.",
        )
    retry_after = limiter.retry_after(str(current_user["id"]))
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Se alcanzó el límite temporal de consultas de IA.",
            headers={"Retry-After": str(retry_after)},
        )