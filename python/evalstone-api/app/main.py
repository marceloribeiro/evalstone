import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app import __version__
from app.config import get_settings
from app.errors import DomainError
from app.routers import health

settings = get_settings()

app = FastAPI(
    title="Evalstone API",
    version=__version__,
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


@app.exception_handler(DomainError)
def domain_error_handler(_: Request, err: DomainError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if err.status == 401 else None
    return JSONResponse(status_code=err.status, content={"detail": err.detail}, headers=headers)


_basic = HTTPBasic()


def _docs_guard(credentials: HTTPBasicCredentials = Depends(_basic)) -> None:
    ok_user = secrets.compare_digest(credentials.username, settings.docs_username)
    ok_pass = secrets.compare_digest(credentials.password, settings.docs_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(_docs_guard)])
def openapi_json():
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


@app.get("/docs", include_in_schema=False, dependencies=[Depends(_docs_guard)])
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} docs")
