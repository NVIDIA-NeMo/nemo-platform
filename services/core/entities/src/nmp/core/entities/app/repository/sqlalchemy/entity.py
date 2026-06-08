# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SQLAlchemy implementation of Entity repository."""

from asyncio import Lock
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from nmp.common.api.filter import FilterOperation
from nmp.common.entities import ALL_WORKSPACES
from nmp.core.entities.app.repository.entity import EntityRepositoryInterface
from nmp.core.entities.app.repository.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    EntityVersionConflictError,
)
from nmp.core.entities.app.repository.sqlalchemy.filter import SQLAlchemyFilterRepository
from nmp.core.entities.app.repository.sqlalchemy.models import DBEntity
from nmp.core.entities.entities import Entity
from nmp.core.entities.utils.identifiers import generate_entity_id
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError


def _is_unique_violation(err: IntegrityError) -> bool:
    """Return True if an IntegrityError was caused by a uniqueness constraint.

    Centralises the driver-message sniffing so callers can rely on the typed
    ``EntityAlreadyExistsError`` instead of matching strings themselves.
    """
    msg = str(getattr(err, "orig", err)).lower()
    return "duplicate key" in msg or "unique constraint" in msg or "unique constraint failed" in msg


class SQLAlchemyEntityRepository(EntityRepositoryInterface):
    """SQLAlchemy implementation of Entity repository."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker
        self._write_lock = Lock()

    def _is_sqlite(self, session: AsyncSession) -> bool:
        bind = session.get_bind()
        return bind.dialect.name == "sqlite"

    @asynccontextmanager
    async def _get_session(
        self, session: AsyncSession | None, *, for_write: bool = False
    ) -> AsyncIterator[AsyncSession]:
        """Get or create a database session.

        When the caller supplies a ``session`` it owns the session's lifecycle,
        including the SQLite write lock (acquired once in :meth:`transaction`).
        We therefore must not re-acquire the lock here — ``asyncio.Lock`` is not
        reentrant, so doing so would deadlock nested writes within a transaction.
        """
        if session is not None:
            yield session
        else:
            async with self.session_maker() as new_session:
                if for_write and self._is_sqlite(new_session):
                    async with self._write_lock:
                        yield new_session
                else:
                    yield new_session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Begin a transaction and yield a session to thread through write calls.

        Pass the yielded session into ``create_entity`` / ``update_entity_by_name``
        / etc. to make several writes commit (or roll back) atomically. This keeps
        transaction lifecycle ownership inside the repository so callers don't have
        to reach for the session maker or know about ``session.begin()``.
        """
        async with self._get_session(None, for_write=True) as session:
            async with session.begin():
                yield session

    def _get_sort_key(self, sort: str) -> Any:
        reverse = sort.startswith("-")
        sort_key = sort.lstrip("-")

        if sort_key.startswith("data."):
            path = sort_key.split(".")[1:]
            result = DBEntity.data
            for key in path:
                result = result[key]
            return result.desc() if reverse else result.asc()

        if hasattr(DBEntity, sort_key):
            return getattr(DBEntity, sort_key).desc() if reverse else getattr(DBEntity, sort_key).asc()

        raise ValueError(f"Invalid sort field {sort_key}")

    async def create_entity(
        self,
        *,
        workspace: str,
        entity_type: str,
        name: str,
        data: Dict[str, Any],
        parent: str | None = None,
        project: str | None = None,
        created_by: str | None = None,
        session: AsyncSession | None = None,
    ) -> Entity:
        """Create a new entity."""
        async with self._get_session(session, for_write=True) as sess:
            entity_id = generate_entity_id(entity_type)

            db_entity = DBEntity(
                id=entity_id,
                workspace=workspace,
                entity_type=entity_type,
                name=name,
                parent=parent,
                project=project,
                created_by=created_by,
                data=data,
            )

            sess.add(db_entity)
            try:
                if session is not None:
                    await sess.flush()
                else:
                    await sess.commit()
                    await sess.refresh(db_entity)
            except IntegrityError as err:
                if _is_unique_violation(err):
                    raise EntityAlreadyExistsError(
                        f"Entity '{name}' of type '{entity_type}' already exists in workspace '{workspace}'"
                    ) from err
                raise

            return db_entity.to_pydantic()

    async def get_entity_by_id(
        self,
        *,
        entity_id: str,
        session: AsyncSession | None = None,
    ) -> Optional[Entity]:
        """Get an entity by id."""
        async with self._get_session(session) as sess:
            result = await sess.execute(select(DBEntity).where(DBEntity.id == entity_id))
            db_entity = result.scalar_one_or_none()
            if db_entity is None:
                return None

            return db_entity.to_pydantic()

    async def get_entity_by_name(
        self,
        *,
        workspace: str,
        entity_type: str,
        name: str,
        parent: Optional[str] = None,
        session: AsyncSession | None = None,
    ) -> Optional[Entity]:
        """Get an entity by workspace, type, and name, optionally scoped to a parent.

        With the unique constraint on (workspace, entity_type, parent, name),
        this will return exactly one entity or None.
        """
        async with self._get_session(session) as sess:
            query = select(DBEntity).where(
                DBEntity.workspace == workspace,
                DBEntity.entity_type == entity_type,
                DBEntity.name == name,
            )
            if parent is None:
                query = query.where(DBEntity.parent.is_(None))
            else:
                query = query.where(DBEntity.parent == parent)

            result = await sess.execute(query)
            db_entity = result.scalar_one_or_none()

            if db_entity is None:
                return None

            return db_entity.to_pydantic()

    async def list_entities(
        self,
        *,
        workspace: str,
        entity_type: str | None = None,
        page: int = 1,
        page_size: int = 100,
        sort: Optional[str] = None,
        filter_op: Optional[FilterOperation] = None,
        relationship_child_workspaces: Optional[set[str]] = None,
        session: AsyncSession | None = None,
    ) -> tuple[List[Entity], int]:
        """List entities with filtering."""
        async with self._get_session(session) as sess:
            # Start with base query
            query = select(DBEntity)

            # Apply entity type filter if specified
            if entity_type is not None:
                query = query.where(DBEntity.entity_type == entity_type)

            # Apply workspace filtering if specified
            if workspace != ALL_WORKSPACES:
                query = query.where(DBEntity.workspace == workspace)
            # If workspace is ALL_WORKSPACES, query all workspaces (access control via filter)

            if filter_op is not None:
                filter_repo = SQLAlchemyFilterRepository(
                    DBEntity, relationship_child_workspaces=relationship_child_workspaces
                )
                query = query.where(filter_op.apply(filter_repo))

            count_query = select(func.count()).select_from(query.subquery())
            total_result = await sess.execute(count_query)
            total = total_result.scalar() or 0

            if sort is not None:
                query = query.order_by(self._get_sort_key(sort))
            else:
                query = query.order_by(DBEntity.created_at.desc())

            query = query.offset((page - 1) * page_size).limit(page_size)

            result = await sess.execute(query)
            db_entities = result.scalars().all()

            entities = [e.to_pydantic() for e in db_entities]

            return entities, total

    async def update_entity(
        self,
        *,
        entity_id: str,
        data: Dict[str, Any],
        name: str | None = None,
        project: str | None = None,
        updated_by: str | None = None,
        session: AsyncSession | None = None,
    ) -> Entity:
        """Update an entity by ID, optionally changing its name."""
        async with self._get_session(session, for_write=True) as sess:
            result = await sess.execute(select(DBEntity).where(DBEntity.id == entity_id))
            existing_entity = result.scalar_one_or_none()
            if existing_entity is None:
                raise EntityNotFoundError(f"Entity with ID '{entity_id}' not found")

            existing_entity.data = data
            if name is not None:
                existing_entity.name = name
            if project is not None:
                existing_entity.project = project
            if updated_by is not None:
                existing_entity.updated_by = updated_by
            try:
                await sess.commit()
            except StaleDataError as err:
                raise EntityVersionConflictError(
                    f"Entity with ID '{entity_id}' was modified by another request. Please refetch and retry."
                ) from err
            await sess.refresh(existing_entity)

            return existing_entity.to_pydantic()

    async def update_entity_by_name(
        self,
        *,
        workspace: str,
        entity_type: str,
        name: str,
        data: Dict[str, Any],
        new_name: str | None = None,
        parent: str | None = None,
        project: str | None = None,
        clear_project: bool = False,
        updated_by: str | None = None,
        expected_db_version: int | None = None,
        session: AsyncSession | None = None,
    ) -> Entity:
        """Update an entity by name, optionally changing its name.

        Pass ``clear_project=True`` alongside ``project=None`` to explicitly
        disassociate the entity from its current project.  Without this flag,
        ``project=None`` is treated as "no change" for backward-compatibility.
        """
        async with self._get_session(session, for_write=True) as sess:
            query = select(DBEntity).where(
                DBEntity.workspace == workspace,
                DBEntity.entity_type == entity_type,
                DBEntity.name == name,
            )
            if parent is None:
                query = query.where(DBEntity.parent.is_(None))
            else:
                query = query.where(DBEntity.parent == parent)

            result = await sess.execute(query)
            existing_entity = result.scalar_one_or_none()
            if existing_entity is None:
                raise EntityNotFoundError(
                    f"Entity '{name}' of type '{entity_type}' not found in workspace '{workspace}'"
                )

            # Check expected_db_version atomically in the same transaction
            if expected_db_version is not None and existing_entity.db_version != expected_db_version:
                raise EntityVersionConflictError(
                    f"Entity '{name}' of type '{entity_type}' in workspace '{workspace}' was modified by another request. "
                    f"Expected version {expected_db_version}, but current version is {existing_entity.db_version}. Please refetch and retry."
                )

            existing_entity.data = data
            if new_name is not None:
                existing_entity.name = new_name
            if project is not None:
                existing_entity.project = project
            elif clear_project:
                existing_entity.project = None
            if updated_by is not None:
                existing_entity.updated_by = updated_by
            try:
                if session is not None:
                    await sess.flush()
                else:
                    await sess.commit()
                    await sess.refresh(existing_entity)
            except StaleDataError as err:
                raise EntityVersionConflictError(
                    f"Entity '{name}' of type '{entity_type}' in workspace '{workspace}' was modified by another request. Please refetch and retry."
                ) from err

            return existing_entity.to_pydantic()

    async def delete_entity(
        self,
        *,
        entity_id: str,
        session: AsyncSession | None = None,
    ) -> int:
        """Delete an entity by ID."""
        async with self._get_session(session, for_write=True) as sess:
            result = await sess.execute(select(DBEntity).where(DBEntity.id == entity_id))
            existing_entity = result.scalar_one_or_none()
            if existing_entity is None:
                return 0

            await sess.delete(existing_entity)
            await sess.commit()
            return 1

    async def delete_entity_by_name(
        self,
        *,
        workspace: str,
        entity_type: str,
        name: str,
        parent: Optional[str] = None,
        session: AsyncSession | None = None,
    ) -> int:
        """Delete an entity by name."""
        async with self._get_session(session, for_write=True) as sess:
            query = select(DBEntity).where(
                DBEntity.workspace == workspace,
                DBEntity.entity_type == entity_type,
                DBEntity.name == name,
            )
            if parent is None:
                query = query.where(DBEntity.parent.is_(None))
            else:
                query = query.where(DBEntity.parent == parent)

            result = await sess.execute(query)
            existing_entity = result.scalar_one_or_none()
            if existing_entity is None:
                return 0

            await sess.delete(existing_entity)
            await sess.commit()
            return 1
