import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.database.database import Database
from api.routes import executions, health
from api.scheduler.scheduler import JobScheduler

db = Database()
scheduler = JobScheduler(database=db, max_concurrency=10, max_queue_size=100)

executions.init_dependencies(db, scheduler)
health.init_dependencies(db, scheduler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect DB, recover stale/interrupted jobs, start workers
    await db.connect()
    recovered = await db.recover_stale_executions()
    if recovered > 0:
        print(f"[runbox-api] Recovered {recovered} stale execution(s) from prior session.")
    await scheduler.start()
    yield
    # Shutdown: stop scheduler workers and close DB
    await scheduler.stop()
    await db.close()


app = FastAPI(
    title="Runbox Secure Execution API",
    version="0.1.1",
    description="High-security Linux-based sandboxed code execution infrastructure with multi-layer defense-in-depth",
    lifespan=lifespan,
)


# Request body size limiter middleware (1 MB limit)
class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, max_content_length: int = 1048576):
        super().__init__(app)
        self.max_content_length = max_content_length

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_content_length:
                    return JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={
                            "detail": f"Payload exceeds maximum allowed size of {self.max_content_length} bytes."
                        },
                    )
            except ValueError:
                pass
        return await call_next(request)


app.add_middleware(RequestBodySizeLimitMiddleware, max_content_length=1048576)

# CORS middleware for local developer dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(executions.router)
app.include_router(health.router)

# Mount developer dashboard static assets if built
dashboard_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dashboard", "dist"))
if os.path.exists(dashboard_dist):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=dashboard_dist, html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn

    # Default host is strictly 127.0.0.1 per Security Rule 3.1
    host = os.environ.get("RUNBOX_HOST", "127.0.0.1")
    port = int(os.environ.get("RUNBOX_PORT", "8000"))
    uvicorn.run("api.main:app", host=host, port=port, reload=False)
