"""
TraceWise integration test app.

Run with:
    docker compose up --build

Then visit:
    http://localhost:8000/health          — simple route
    http://localhost:8000/echo-traceparent — echoes inbound traceparent header
    http://localhost:8000/proxy-traceparent — async outbound traceparent demo
    http://localhost:8000/proxy-traceparent-sync — sync outbound traceparent demo
    http://localhost:8000/proxy-traceparent-custom — preserves caller traceparent
    http://localhost:8000/users           — list with child span + log event
    http://localhost:8000/users/42        — path param + decorated function
    http://localhost:8000/orders          — POST with two child spans
    http://localhost:8000/db-users        — async SQLAlchemy SELECT demo
    http://localhost:8000/db-users        — POST sync SQLAlchemy INSERT demo
    http://localhost:8000/slow            — artificial delay
    http://localhost:8000/error           — raises exception
    http://localhost:8000/tracewise       — viewer UI
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

import httpx
import tracewise
from fastapi import FastAPI, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)

_DEMO_DB_PATH = Path.home() / ".tracewise" / "demo.sqlite3"
_SYNC_DB_URL = f"sqlite:///{_DEMO_DB_PATH}"
_ASYNC_DB_URL = f"sqlite+aiosqlite:///{_DEMO_DB_PATH}"

sync_db_engine = create_engine(_SYNC_DB_URL)
async_db_engine = create_async_engine(_ASYNC_DB_URL)


def _seed_demo_db() -> None:
    _DEMO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_db_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS demo_users ("
                "id INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL)"
            )
        )
        existing = conn.execute(text("SELECT COUNT(*) FROM demo_users")).scalar_one()
        if existing == 0:
            conn.execute(
                text(
                    "INSERT INTO demo_users (name) VALUES "
                    "('Alice'), ('Bob')"
                )
            )


_seed_demo_db()

app = FastAPI(title="TraceWise Test App")
tracewise.init(
    app,
    capture_logs=logging.INFO,
    instrument_httpx=True,
    instrument_sqlalchemy=True,
)


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/echo-traceparent")
async def echo_traceparent(request: Request):
    return {"traceparent": request.headers.get("traceparent")}


@app.get("/proxy-traceparent")
async def proxy_traceparent():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        response = await client.get("/echo-traceparent")
    return response.json()


@app.get("/proxy-traceparent-sync")
def proxy_traceparent_sync():
    with httpx.Client(base_url="http://127.0.0.1:8000") as client:
        response = client.get("/echo-traceparent")
    return response.json()


@app.get("/proxy-traceparent-custom")
async def proxy_traceparent_custom():
    existing = "00-11111111111111111111111111111111-2222222222222222-01"
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        response = await client.get(
            "/echo-traceparent",
            headers={"traceparent": existing},
        )
    return response.json()


@app.get("/proxy-health")
async def proxy_health():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        response = await client.get("/health")
    return response.json()


@app.get("/proxy-health-sync")
def proxy_health_sync():
    with httpx.Client(base_url="http://127.0.0.1:8000") as client:
        response = client.get("/health")
    return response.json()


@app.get("/users")
async def list_users():
    logger.info("Fetching users from database")
    async with tracewise.start_span("db.query", table="users", operation="SELECT"):
        await asyncio.sleep(0.01)
    tracewise.set_attribute("result.count", 2)
    return {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await fetch_user(user_id)
    return {"user": user}


@tracewise.trace_span("fetch_user", attributes=lambda user_id, **_: {"user.id": str(user_id)})
async def fetch_user(user_id: int) -> dict:
    logger.debug("Fetching user %s", user_id)
    await asyncio.sleep(0.005)
    return {"id": user_id, "name": f"User {user_id}"}


class OrderBody(BaseModel):
    product: str
    quantity: int


class DemoUserBody(BaseModel):
    name: str


@app.post("/orders")
async def create_order(body: OrderBody):
    tracewise.set_attributes({"order.product": body.product, "order.quantity": body.quantity})
    logger.info("Creating order for product=%s qty=%s", body.product, body.quantity)
    async with tracewise.start_span("validate.order", product=body.product):
        await asyncio.sleep(0.002)
    async with tracewise.start_span("db.insert", table="orders"):
        await asyncio.sleep(0.008)
    return {"order": "created", "product": body.product}


@app.get("/db-users")
async def list_db_users():
    async with async_db_engine.connect() as conn:
        result = await conn.execute(text("SELECT id, name FROM demo_users ORDER BY id"))
        return {"users": [dict(row) for row in result.mappings().all()]}


@app.post("/db-users")
def create_db_user(body: DemoUserBody):
    with sync_db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO demo_users (name) VALUES (:name)"),
            {"name": body.name},
        )
    return {"created": body.name}


@app.get("/slow")
async def slow():
    await asyncio.sleep(0.5)
    return {"message": "that was slow"}


@app.get("/error")
async def error():
    logger.error("About to raise intentional error")
    raise RuntimeError("intentional error for testing")
