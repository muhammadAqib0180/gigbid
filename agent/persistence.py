"""Checkpointer + store factory: Postgres (AsyncPostgresSaver/AsyncPostgresStore) when DATABASE_URL is
Postgres (docker compose / deployment), SQLite otherwise (laptop, tests). Same LangGraph APIs either way."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from agent.settings import database_url, is_postgres, processed_dir


@asynccontextmanager
async def persistence():
    """Yields (checkpointer, store). Long-lived: open once per process (API lifespan / worker startup)."""
    if is_postgres():
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        conninfo = database_url().replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
        pool = AsyncConnectionPool(conninfo, max_size=10, open=False,
                                   kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        await pool.open()
        try:
            cp = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
            await cp.setup()
            store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
            await store.setup()
            yield cp, store
        finally:
            await pool.close()
    else:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.store.sqlite.aio import AsyncSqliteStore

        path = Path(processed_dir() / "checkpoints.sqlite")
        conn = await aiosqlite.connect(str(path), timeout=30)
        conn2 = await aiosqlite.connect(str(processed_dir() / "memory_store.sqlite"), timeout=30, isolation_level=None)
        for c in (conn, conn2):
            await c.execute("PRAGMA journal_mode=WAL")
            await c.execute("PRAGMA busy_timeout=30000")
        import asyncio

        class SerializedSqliteStore(AsyncSqliteStore):
            """One aiosqlite connection cannot run overlapping transactions; serialise store batches."""

            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self._gigbid_lock = asyncio.Lock()

            async def abatch(self, ops):
                async with self._gigbid_lock:
                    return await super().abatch(ops)

        try:
            cp = AsyncSqliteSaver(conn)
            await cp.setup()
            store = SerializedSqliteStore(conn2)
            await store.setup()
            yield cp, store
        finally:
            await conn.close()
            await conn2.close()


def thread_config(thread_id: str, **extra: Any) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id, **extra}}
