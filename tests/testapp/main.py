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
    http://localhost:8000/slow            — artificial delay
    http://localhost:8000/error           — raises exception
    http://localhost:8000/tracewise       — viewer UI
"""
import asyncio
import logging
from datetime import datetime

import httpx
import tracewise
from fastapi import FastAPI, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="TraceWise Test App")
tracewise.init(app, capture_logs=logging.INFO, instrument_httpx=True)


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


@app.post("/orders")
async def create_order(body: OrderBody):
    tracewise.set_attributes({"order.product": body.product, "order.quantity": body.quantity})
    logger.info("Creating order for product=%s qty=%s", body.product, body.quantity)
    async with tracewise.start_span("validate.order", product=body.product):
        await asyncio.sleep(0.002)
    async with tracewise.start_span("db.insert", table="orders"):
        await asyncio.sleep(0.008)
    return {"order": "created", "product": body.product}


@app.get("/slow")
async def slow():
    await asyncio.sleep(0.5)
    return {"message": "that was slow"}


@app.get("/error")
async def error():
    logger.error("About to raise intentional error")
    raise RuntimeError("intentional error for testing")
