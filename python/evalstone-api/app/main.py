import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.exc import IntegrityError

from app import __version__
from app.config import get_settings
from app.errors import DomainError
from app.routers import (
    auth,
    datasets,
    health,
    labels,
    organizations,
    projects,
    providers,
    runs,
)

settings = get_settings()

app = FastAPI(
    title="Evalstone API",
    version=__version__,
    description="The Evalstone center: the sole owner of PostgreSQL (ADR-001).",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,  # served below, behind basic auth
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(providers.router)
app.include_router(datasets.router)
app.include_router(runs.router)
app.include_router(labels.router)


@app.exception_handler(DomainError)
def domain_error_handler(_: Request, err: DomainError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if err.status == 401 else None
    return JSONResponse(status_code=err.status, content={"detail": err.detail}, headers=headers)


@app.exception_handler(IntegrityError)
def integrity_error_handler(_: Request, err: IntegrityError) -> JSONResponse:
    """Services pre-check uniqueness for a good message; a concurrent insert still lands here."""
    return JSONResponse(status_code=409, content={"detail": "conflicts with an existing record"})


_basic = HTTPBasic()


def _docs_guard(credentials: HTTPBasicCredentials = Depends(_basic)) -> None:
    # compare on bytes: compare_digest raises TypeError on non-ASCII str (→ 500 instead of 401)
    ok_user = secrets.compare_digest(credentials.username.encode(), settings.docs_username.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), settings.docs_password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(_docs_guard)])
def openapi_json():
    return app.openapi()  # FastAPI's own cached schema, with description/tags/servers intact


@app.get("/docs", include_in_schema=False, dependencies=[Depends(_docs_guard)])
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} docs")
