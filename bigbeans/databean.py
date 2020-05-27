"""
The MIT License

Copyright (c) 2020 Kaylynn Morgan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from typing import Sequence, Optional, Iterable, AnyStr
from uuid import UUID
from ipaddress import IPv4Network, IPv6Network, IPv4Interface, IPv6Interface, IPv4Address, IPv6Address
from datetime import datetime, date, time
from collections import Mapping, defaultdict
from decimal import Decimal

import asyncpg
from asyncpg import Range, Record, BitString, Box, Circle, Line, LineSegment, Path, Point, Polygon

VALID_TYPE_MAPPING = defaultdict(lambda: "text")
TYPE_MAPPING = {
    list: "anyarray",
    str: "text",
    bool: "bool",
    bytes: "bytea",
    int: "bigint",
    float: "float8",
    tuple: "record",
    Mapping: "record",
    Range: "anyrange",
    Record: "record",
    BitString: "varbit",
    Box: "box",
    Circle: "circle",
    Line: "line",
    LineSegment: "lseg",
    Path: "path",
    Point: "point",
    Polygon: "polygon",
    Decimal: "numeric",
    IPv4Network: "inet",
    IPv6Network: "inet",
    IPv4Interface: "inet",
    IPv6Interface: "inet",
    IPv4Address: "inet",
    IPv6Address: "inet",
    UUID: "uuid",
    date: "date",
    time: "timestamp",
    datetime: "timestamptz"
}

VALID_TYPE_MAPPING.update(TYPE_MAPPING)


class BeansError(Exception):
    pass


class Table:
    """
    ...
    """

    def __init__(self, name, bean):
        self._name = name
        self._bean = bean

    async def _ensure_beans(self, to_bean: dict) -> None:
        async with self._bean._pool.acquire() as connection:
            results = await connection.fetchrow("SELECT * FROM pg_tables WHERE tablename = $1", self._name)
            if not results:  # no existing table, safe to create
                table_details = []
                for i, (key, value) in enumerate(to_bean.items(), start=1):
                    table_details.append(f"{key} {VALID_TYPE_MAPPING[type(value)]}")

                joined = ",\n                    ".join(table_details)
                query = f"""
                    CREATE TABLE {self._name}(
                        _id serial PRIMARY KEY,
                        {joined}
                    );
                    """

                await connection.execute(query)

            else:  # table exists, add new columns
                table_details = []
                for i, (key, value) in enumerate(to_bean.items(), start=1):
                    table_details.append(f"ADD COLUMN IF NOT EXISTS {key} {VALID_TYPE_MAPPING[type(value)]}")

                column_query_as_string = ',\n'.join(table_details)
                await connection.execute(
                    f"""
                    ALTER TABLE {self._name}
                    {column_query_as_string};
                    """
                )

    async def _build_insert_query(self, **kwargs) -> str:
        # the insert function should make sure we're not inserting nothing, so no need to do so here
        query_names = f"({', '.join(kwargs.keys())})"
        query_values = f"({', '.join([f'${i + 1}' for i in range(len(kwargs.values()))])})"

        return f"INSERT INTO {self._name}{query_names} VALUES{query_values}"

    async def _build_select_query(self, **kwargs) -> str:
        # the find function(s) will make sure we're not trying to find nothing, so no need to do so here
        base = f"SELECT * FROM {self._name} WHERE {list(kwargs.keys())[0]} = $1"
        if len(kwargs) == 1:
            return base

        additional_constraints = [f" AND {k} = ${i}" for i, k in enumerate(list(kwargs.keys())[1:], start=2)]

        return f"{base}{' '.join(additional_constraints)};"

    async def _build_update_query(self, match, **kwargs) -> str:
        # the update function(s) will make sure we're not trying to update nothing, so no need to do so here
        matched_values = {k: v for k, v in kwargs.items() if k in match}
        query_values = ', '.join([f"{k} = ${i + 1}" for i, k in enumerate(kwargs.keys())])
        constraint_values = [
            f"{k} = ${i + 1}" for i, k in enumerate(matched_values.keys(), start=len(matched_values.keys()) + 1)
        ]

        query = f"UPDATE {self._name} SET {query_values} WHERE {', '.join(constraint_values)};"
        for_statement = list(kwargs.values()) + list(matched_values.values())

        return query, for_statement

    async def all(self) -> Sequence[asyncpg.Record]:
        """
        Returns a `list` of all records in this table represented as `asyncpg.Record` objects.
        These have a similar interface to `dict` and are read-only.
        """

        async with self._bean._pool.acquire() as connection:
            try:
                return await connection.fetch(f"SELECT * FROM {self._name};")
            except asyncpg.UndefinedTableError:
                return []

    async def find(self, **kwargs) -> Sequence[asyncpg.Record]:
        """
        Performs a simple search on the table. Pass keyword arguments to filter rows by value.
        Returns a `list` of `asyncpg.Record` objects - these have a similar interface to `dict` and are read-only.
        """

        async with self._bean._pool.acquire() as connection:
            try:
                if kwargs:
                    query = await self._build_select_query(**kwargs)
                    return await connection.fetch(query, *kwargs.values())
                else:
                    return await self.all()
            except asyncpg.UndefinedTableError:
                return []

    async def find_one(self, **kwargs) -> Optional[asyncpg.Record]:
        """
        Similar to `find`, but returns a single `asyncpg.Record`, or None.
        """

        async with self._bean._pool.acquire() as connection:
            try:
                if kwargs:
                    query = await self._build_select_query(**kwargs)
                    return await connection.fetchrow(query, *kwargs.values())
                else:
                    return await connection.fetchrow(f"SELECT * FROM {self._name} LIMIT 1;")
            except asyncpg.UndefinedTableError:
                return None

    async def insert(self, **kwargs) -> None:
        """
        Inserts items into the table. Keyword arguments denote row values.
        """

        if not kwargs:
            raise BeansError("Bad insert call - you attempted to insert nothing. Don't do this.")

        await self._ensure_beans(kwargs)
        query = await self._build_insert_query(**kwargs)
        async with self._bean._pool.acquire() as connection:
            await connection.execute(query, *kwargs.values())

    async def update(self, match: Sequence[AnyStr], **kwargs) -> None:
        """
        ...
        """

        if not kwargs:
            raise BeansError("Bad upsert call - you attempted to update nothing. Don't do this.")

        await self._ensure_beans(kwargs)
        query, values = await self._build_update_query(match, **kwargs)
        async with self._bean._pool.acquire() as connection:
            await connection.execute(query, *values)

    async def upsert(self, match: Sequence[AnyStr], **kwargs) -> None:
        """
        ...
        """

        if not kwargs:
            raise BeansError("Bad upsert call - you attempted to upsert nothing. Don't do this.")

        await self._ensure_beans(kwargs)
        matching_kwargs = {k: v for k, v in kwargs.items() if k in match}
        found = await self.find_one(**matching_kwargs)
        if found:
            await self.update(match + ["_id"], **kwargs)
        else:
            await self.insert(**kwargs)

    async def drop(self) -> None:
        """
        Give up on this table and get rid of it - this will remove schema and delete all records.
        """

        async with self._bean._pool.acquire() as connection:
            await connection.execute(f"DROP TABLE {self._name};")

        del self._bean._tables[self._name]

    async def delete(self, **kwargs) -> None:
        """
        Deletes rows from the table. Pass keyword arguments to filter rows to delete by value.
        If no keywords are given, all records are deleted.
        """

        async with self._bean._pool.acquire() as connection:
            if kwargs:
                query = await self._build_select_query(**kwargs).replace("SELECT *", "DELETE", 1)
                await connection.execute(query, *kwargs.values())
            else:
                await connection.execute(f"DELETE FROM {self._name};")


class Databean():
    """
    Thos beans.
    """

    def __getitem__(self, key) -> Table:
        if key not in self._tables:
            self._tables[key] = Table(key, self)

        return self._tables[key]

    def __len__(self) -> int:
        return len(self._tables)

    def __iter__(self) -> Iterable[Table]:
        return iter(self._tables)

    @staticmethod
    async def _connect(*args, **kwargs):
        new = Databean()
        new._pool = await asyncpg.create_pool(**kwargs)
        new._tables = {}  # tables are fetched lazily

        return new

    async def close(self, timeout: int = None):
        await self._pool.close(timeout=timeout)
        del self

    async def execute_query(self, query_string, *args, **kwargs):
        """Executes a plain SQl instruction."""

        async with self._pool.acquire() as connection:
            await connection.execute(query_string, *args, **kwargs)

    async def fetch_query(self, query_string, *args, **kwargs):
        """Executes a plain SQl query. This will return whatever results are found in their usual formats."""

        async with self._pool.acquire() as connection:
            res = await connection.fetch(query_string, *args, **kwargs)

        return res
