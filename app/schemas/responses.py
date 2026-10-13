from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ErrorDetail(BaseModel):
    field: str
    code: str
    message: str


class Meta(BaseModel):
    model_config = {"extra": "allow"}


class PaginationMeta(Meta):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class BaseResponse(BaseModel, Generic[T]):
    success: bool
    code: int | str
    message: str
    data: T | None = None
    errors: list[ErrorDetail] | None = None
    meta: dict[str, Any] | None = None
    requestId: str
    timestamp: str = Field(default_factory=utc_timestamp)

    @classmethod
    def ok(
        cls,
        *,
        data: T | None,
        code: int | str = 200,
        message: str = "Success",
        meta: Meta | dict[str, Any] | None = None,
        request_id: str,
    ) -> "BaseResponse[T]":
        return cls(
            success=True,
            code=code,
            message=message,
            data=data,
            meta=_meta_dict(meta),
            requestId=request_id,
        )

    @classmethod
    def failure(
        cls,
        *,
        code: int | str,
        message: str,
        errors: list[ErrorDetail] | None,
        request_id: str,
        data: T | None = None,
        meta: Meta | dict[str, Any] | None = None,
    ) -> "BaseResponse[T]":
        return cls(
            success=False,
            code=code,
            message=message,
            data=data,
            errors=errors,
            meta=_meta_dict(meta),
            requestId=request_id,
        )


def success_response(
    *,
    data: T | None,
    request_id: str,
    code: int | str = 200,
    message: str = "Success",
    meta: Meta | dict[str, Any] | None = None,
) -> BaseResponse[T]:
    return BaseResponse.ok(
        data=data,
        code=code,
        message=message,
        meta=meta,
        request_id=request_id,
    )


def error_response(
    *,
    code: int | str,
    message: str,
    request_id: str,
    errors: list[ErrorDetail] | None = None,
    data: T | None = None,
    meta: Meta | dict[str, Any] | None = None,
) -> BaseResponse[T]:
    return BaseResponse.failure(
        code=code,
        message=message,
        errors=errors,
        request_id=request_id,
        data=data,
        meta=meta,
    )


def _meta_dict(meta: Meta | dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(meta, BaseModel):
        return meta.model_dump(mode="json")
    return meta
