"""官方 async saver 的独立连接；不把 checkpoint 包入业务事务。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from commerceops.infrastructure.database import DatabaseSettings


@asynccontextmanager
async def checkpointer(settings: DatabaseSettings) -> AsyncIterator[AsyncPostgresSaver]:
    async with await AsyncConnection.connect(
        **settings.kwargs(),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
        options="-c search_path=checkpoints -c timezone=UTC",
    ) as connection:
        yield AsyncPostgresSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=[]))
