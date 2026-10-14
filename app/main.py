import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from app.db.session import app_session_factory, dispose_engines
from app.middleware.request_context import RequestContextMiddleware


async def _booking_lifecycle_worker():
    while True:
        try:
            async with app_session_factory() as session:
                await session.execute(
                    text(
                        """
                        UPDATE booking
                        SET status = 'COMPLETED', completed_at = NOW(), updated_at = NOW()
                        WHERE status = 'CONFIRMED'
                          AND TIMESTAMP(booking_date, end_time) < NOW() - INTERVAL 30 MINUTE
                        """
                    )
                )
                await session.commit()
        except Exception:
            pass
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker_task = asyncio.create_task(_booking_lifecycle_worker())
    yield
    worker_task.cancel()
    with suppress(asyncio.CancelledError):
        await worker_task
    await dispose_engines()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="FitBooking personal training booking API.",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router, prefix=settings.api_v1_prefix)
