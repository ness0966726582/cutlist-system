import os
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://cutlist:cutlist_dev@localhost:15433/cutlist")

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, open=False, kwargs={"row_factory": dict_row})


@contextmanager
def conn():
    with pool.connection() as c:
        yield c


def q1(c, sql, params=()):
    return c.execute(sql, params).fetchone()


def qa(c, sql, params=()):
    return c.execute(sql, params).fetchall()
