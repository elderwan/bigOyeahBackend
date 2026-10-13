from fastapi import APIRouter, HTTPException

from app.core.request_context import get_request_id
from app.schemas.response_demo import UserCreate, UserRead
from app.schemas.responses import BaseResponse, PaginationMeta, success_response

router = APIRouter(prefix="/response-demo")


@router.get("", response_model=BaseResponse[list[UserRead]])
async def list_users() -> BaseResponse[list[UserRead]]:
    users = [
        UserRead(id=1, username="alex", email="alex@example.com"),
        UserRead(id=2, username="maya", email="maya@example.com"),
    ]
    meta = PaginationMeta(page=1, page_size=20, total=2, total_pages=1)
    return success_response(data=users, request_id=get_request_id() or "unknown", meta=meta)


@router.post("", response_model=BaseResponse[UserRead], status_code=201)
async def create_user(payload: UserCreate) -> BaseResponse[UserRead]:
    user = UserRead(id=3, username=payload.username, email=payload.email)
    return success_response(
        data=user,
        code=201,
        message="User created",
        request_id=get_request_id() or "unknown",
    )


@router.get("/http-error")
async def explicit_http_error() -> None:
    raise HTTPException(status_code=404, detail="Demo resource not found")


@router.get("/server-error")
async def unhandled_error() -> None:
    raise RuntimeError("Demo unhandled exception")
