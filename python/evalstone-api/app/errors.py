"""Domain errors raised by services; `app.main` maps them to HTTP statuses.

Services never import FastAPI; routers never touch the database.
"""


class DomainError(Exception):
    status = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    status = 404


class Conflict(DomainError):
    status = 409


class Forbidden(DomainError):
    status = 403


class Unauthorized(DomainError):
    status = 401


class Invalid(DomainError):
    status = 422
