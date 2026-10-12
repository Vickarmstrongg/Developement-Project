from fastapi import HTTPException


def require_admin():
    raise HTTPException(
        status_code=503,
        detail="Admin authentication is not configured.",
    )
