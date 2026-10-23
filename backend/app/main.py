from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.api_locale import english_requested, translate_error, add_error_code
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.db import engine, Base
from app.api import scans, catalog, dns, project_transfer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы при старте
    Base.metadata.create_all(bind=engine)
    from app.core.migrations import migrate
    migrate(engine)
    print(f"✅ {settings.APP_NAME} v{settings.APP_VERSION} started")
    yield
    print(f"👋 {settings.APP_NAME} stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Web Scanner — rustscan + nmap + httpx + gowitness",
    lifespan=lifespan,
)

@app.exception_handler(StarletteHTTPException)
async def localized_http_error(request: Request, exc: StarletteHTTPException):
    if english_requested(request.headers.get('accept-language', '')) and isinstance(exc.detail, str):
        exc = StarletteHTTPException(exc.status_code, translate_error(exc.detail), headers=exc.headers)
    response = add_error_code(await http_exception_handler(request, exc), exc.status_code)
    response.headers['Vary'] = 'Accept-Language'
    return response


@app.exception_handler(RequestValidationError)
async def localized_validation_error(request: Request, exc: RequestValidationError):
    if english_requested(request.headers.get('accept-language', '')):
        errors = [dict(error, msg=translate_error(error['msg'])) for error in exc.errors()]
        exc = RequestValidationError(errors, body=exc.body)
    response = add_error_code(await request_validation_exception_handler(request, exc), 422)
    response.headers['Vary'] = 'Accept-Language'
    return response


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(project_transfer.router)
app.include_router(dns.router)
app.include_router(scans.router)
app.include_router(catalog.router)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
