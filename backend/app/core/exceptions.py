"""
Centralized exception handling (Milestone 19).

FastAPI's own default already produces a consistent `{"detail": "<string>"}`
shape for every `HTTPException` raised by the routers — that convention
was followed from Milestone 5 onward (one `except SomeServiceError as exc:
raise HTTPException(..., detail=str(exc))` block per error case in every
router), and this module doesn't touch that; `register_exception_handlers`
below only adds handlers for the two cases FastAPI/Starlette's defaults
don't already shape consistently, both flagged directly by the roadmap's
own Milestone 19 checklist ("Error responses consistent in shape across
all modules"):

1. Pydantic request-validation failures (422) — FastAPI's own default
   returns `{"detail": [{"type": ..., "loc": [...], "msg": ...}, ...]}`, a
   list of structured error objects, while every other error in this API
   is `{"detail": "<string>"}`. A frontend that assumes `detail` is
   always a string (true for every other 4xx this API returns) would
   break specifically on validation errors.
2. Any *unhandled* exception (a genuine bug, not a deliberate
   HTTPException) — Starlette's default behavior returns a bare-text
   "Internal Server Error" body, not JSON at all, and logs nothing
   structured server-side beyond what the ASGI server itself prints.

Both handlers below normalize to the same `{"detail": "<string>"}` shape,
and the catch-all handler logs the real exception with its full
traceback server-side while returning a generic, non-leaking message to
the client — a 500 body should never describe internal implementation
details (a stack trace, an exception class name, a SQL fragment) to a
caller.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Called once from `main.create_app()`. Kept as an explicit registration
    function (rather than `@app.exception_handler` decorators at this
    module's import time) because there is no module-level `app` here to
    decorate — `create_app()` may build more than one FastAPI instance
    (see main.py's own docstring on why: testing both AI_ENABLED states),
    and each needs its own handlers registered on its own instance.
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Collapse pydantic's structured error list into the same plain-
        # string `detail` shape every HTTPException in this app already
        # returns, e.g. "quantity: Input should be greater than 0".
        messages = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"] if part != "body")
            messages.append(f"{location}: {error['msg']}" if location else error["msg"])
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "; ".join(messages)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred"},
        )
