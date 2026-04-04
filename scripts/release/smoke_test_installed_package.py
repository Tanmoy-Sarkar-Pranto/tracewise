from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI

import tracewise


async def _run_smoke_test(db_path: str) -> None:
    app = FastAPI()
    tracewise.init(app, db_path=db_path)

    async with tracewise.start_span("artifact.smoke") as span:
        assert span is not None

    storage = getattr(app.state, "_tracewise_storage")
    assert storage is not None
    assert any(getattr(route, "path", None) == "/tracewise" for route in app.routes)
    assert storage.list_traces(limit=1)


def main() -> int:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "artifact-smoke.db"
        asyncio.run(_run_smoke_test(str(db_path)))

    print("artifact smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
