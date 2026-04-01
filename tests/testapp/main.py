"""
TraceWise integration test app.

Run with:
    docker compose up --build

Then visit:
    http://localhost:8000/health          — simple route
    http://localhost:8000/users           — list with child span
    http://localhost:8000/users/42        — path param + decorated function
    http://localhost:8000/orders          — POST with two child spans
    http://localhost:8000/slow            — artificial delay
    http://localhost:8000/error           — raises exception
    http://localhost:8000/tracewise       — viewer UI
"""
import asyncio
from datetime import datetime

import tracewise
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="TraceWise Test App")
tracewise.init(app)


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/users")
async def list_users():
    async with tracewise.start_span("db.query", table="users", operation="SELECT"):
        await asyncio.sleep(0.01)
    return {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await fetch_user(user_id)
    return {"user": user}


@tracewise.trace_span("fetch_user", attributes=lambda user_id, **_: {"user.id": str(user_id)})
async def fetch_user(user_id: int) -> dict:
    await asyncio.sleep(0.005)
    return {"id": user_id, "name": f"User {user_id}"}


class OrderBody(BaseModel):
    product: str
    quantity: int


@app.post("/orders")
async def create_order(body: OrderBody):
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
    raise RuntimeError("intentional error for testing")
