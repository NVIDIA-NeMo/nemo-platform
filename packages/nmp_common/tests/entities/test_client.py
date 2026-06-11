# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional
from unittest.mock import AsyncMock, Mock

import pytest
from nemo_platform.types.entities import EntitiesPage, Entity
from nemo_platform.types.shared.pagination_data import PaginationData
from nemo_platform_plugin.entities import _convert_filter_obj_to_filter_str
from nmp.common.auth.models import AuthContext
from nmp.common.entities import (
    ALL_WORKSPACES,
    DEFAULT_WORKSPACE,
    DatetimeFilter,
    EntityBase,
    EntityClient,
    StringFilter,
)
from nmp.common.entities.client import EntityConflictError
from pydantic import BaseModel, Discriminator, Field, PrivateAttr, Tag, computed_field


def test_entity_base_get_data_fields():
    class TestEntity(EntityBase):
        field_1: str
        field_2: str | None
        field_3: int
        field_4: datetime
        field_5: list[str]
        field_6: dict[str, str]
        field_7: float
        field_8: bool
        field_9: bytes
        _field_10: str | None = PrivateAttr(default="some_string")

        @property
        def field_10(self) -> str:
            return self._field_10

        @field_10.setter
        def field_10(self, value: str) -> None:
            self._field_10 = value

    now = datetime.now()
    entity = TestEntity(
        name="test",
        workspace="test",
        field_1="test",
        field_2="test",
        field_3=1,
        field_4=now,
        field_5=["test"],
        field_6={"test": "test"},
        field_7=1.0,
        field_8=True,
        field_9=b"test",
    )
    assert entity._get_data_fields() == {
        "field_1": "test",
        "field_2": "test",
        "field_3": 1,
        "field_4": now.isoformat(),
        "field_5": ["test"],
        "field_6": {"test": "test"},
        "field_7": 1.0,
        "field_8": True,
        "field_9": "test",
        "_field_10": "some_string",
    }


def test_entity_base_convert_api_entity_to_model():
    class TestEntity(EntityBase):
        field_1: str
        field_2: str | None
        field_3: int
        _field_4: str | None = PrivateAttr(default="some_string")

        @property
        def field_4(self) -> str:
            return self._field_4

        @field_4.setter
        def field_4(self, value: str) -> None:
            self._field_4 = value

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={"field_1": "test", "field_2": "test", "field_3": 1, "field_4": "some_string"},
        ),
        TestEntity,
    )
    assert result.field_1 == "test"
    assert result.field_2 == "test"
    assert result.field_3 == 1
    assert result.field_4 == "some_string"
    assert result.id == "123"
    assert result.created_at == now
    assert result.updated_at == now
    assert result.name == "test"
    assert result.workspace == "test"
    assert result._id == "123"
    assert result._created_at == now
    assert result._updated_at == now


def test_entity_base_convert_api_entity_discriminated_union_func():
    class TestEntity(EntityBase):
        a: str

    class TestEntity2(EntityBase):
        b: str

    def discriminator(obj: Any) -> str:
        if "a" in obj:
            return "a"
        return "b"

    EntityUnion = Annotated[
        Annotated[TestEntity, Tag("a")] | Annotated[TestEntity2, Tag("b")], Discriminator(discriminator)
    ]
    setattr(EntityUnion, "__entity_type__", "some_entity")

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="some_entity",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={"a": "test"},
        ),
        EntityUnion,
    )
    assert result.a == "test"
    assert not hasattr(result, "b")
    assert result.id == "123"
    assert result._id == "123"
    assert result._created_at == now
    assert result._updated_at == now


def test_entity_base_convert_api_entity_discriminated_union_field():
    class TestEntity(EntityBase):
        a: str
        type: Literal["a"] = "a"

    class TestEntity2(EntityBase):
        b: str
        type: Literal["b"] = "b"

    EntityUnion = Annotated[TestEntity | TestEntity2, Field(discriminator="type")]
    setattr(EntityUnion, "__entity_type__", "some_entity")

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="some_entity",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={"type": "b", "b": "test"},
        ),
        EntityUnion,
    )
    assert not hasattr(result, "a")
    assert result.b == "test"
    assert result.id == "123"
    assert result._id == "123"
    assert result._created_at == now
    assert result._updated_at == now


def test_entity_base_name_optional_on_input():
    """Test that name is optional when creating an entity."""

    class TestEntity(EntityBase):
        field_1: str

    # Should be able to create entity without specifying name
    entity = TestEntity(
        workspace="test",
        field_1="value",
    )
    assert entity.name == ""
    assert entity.workspace == "test"
    assert entity.field_1 == "value"


def test_entity_base_name_non_nullable_on_output():
    """Test that name is always non-nullable when converting from API response."""

    class TestEntity(EntityBase):
        field_1: str

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test_entity",
            name="generated-name",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={"field_1": "value"},
        ),
        TestEntity,
    )
    # Name should always be present on output
    assert result.name == "generated-name"
    assert isinstance(result.name, str)


def test_entity_base_name_populated_from_api():
    """Test that name from API response populates the entity even when input had no name."""

    class TestEntity(EntityBase):
        field_1: str

    # Create entity without name (simulating input scenario)
    input_entity = TestEntity(
        workspace="test",
        field_1="value",
    )
    assert input_entity.name == ""

    # Simulate API response with generated name
    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test_entity",
            name="api-generated-name",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={"field_1": "value"},
        ),
        TestEntity,
    )
    # Output should have the name from API
    assert result.name == "api-generated-name"
    assert isinstance(result.name, str)


@pytest.mark.asyncio
async def test_entity_client_list_with_all_workspaces_uses_wildcard():
    """Test that list() with workspace=ALL_WORKSPACES passes '-' wildcard to API."""

    class TestEntity(EntityBase):
        field_1: str

    # Mock the entities API
    mock_api = Mock()
    mock_api.list = AsyncMock()
    mock_api.list.return_value = EntitiesPage(
        data=[],
        pagination=PaginationData(page=1, page_size=100, total_pages=0, total_results=0, current_page_size=0),
    )

    client = EntityClient(mock_api)

    # Call list with workspace=ALL_WORKSPACES
    await client.list(TestEntity, workspace=ALL_WORKSPACES)

    # Verify that the API was called with "-" wildcard
    mock_api.list.assert_called_once()
    call_args = mock_api.list.call_args
    assert call_args.args[0] == "test_entity"  # entity type
    assert call_args.kwargs["workspace"] == "-"  # wildcard for all workspaces


@pytest.mark.asyncio
async def test_entity_client_list_with_specific_workspace():
    """Test that list() with specific workspace passes it through to API."""

    class TestEntity(EntityBase):
        field_1: str

    # Mock the entities API
    mock_api = Mock()
    mock_api.list = AsyncMock()
    mock_api.list.return_value = EntitiesPage(
        data=[],
        pagination=PaginationData(page=1, page_size=100, total_pages=0, total_results=0, current_page_size=0),
    )

    client = EntityClient(mock_api)

    # Call list with specific workspace
    await client.list(TestEntity, workspace="my-workspace")

    # Verify that the API was called with the specific workspace
    mock_api.list.assert_called_once()
    call_args = mock_api.list.call_args
    assert call_args.args[0] == "test_entity"
    assert call_args.kwargs["workspace"] == "my-workspace"


@pytest.mark.asyncio
async def test_entity_client_list_with_default_workspace():
    """Test that list() with DEFAULT_WORKSPACE passes it through to API."""

    class TestEntity(EntityBase):
        field_1: str

    # Mock the entities API
    mock_api = Mock()
    mock_api.list = AsyncMock()
    mock_api.list.return_value = EntitiesPage(
        data=[],
        pagination=PaginationData(page=1, page_size=100, total_pages=0, total_results=0, current_page_size=0),
    )

    client = EntityClient(mock_api)

    # Call list with DEFAULT_WORKSPACE explicitly
    await client.list(TestEntity, workspace=DEFAULT_WORKSPACE)

    # Verify that the API was called with DEFAULT_WORKSPACE
    mock_api.list.assert_called_once()
    call_args = mock_api.list.call_args
    assert call_args.args[0] == "test_entity"
    assert call_args.kwargs["workspace"] == DEFAULT_WORKSPACE


@pytest.mark.asyncio
async def test_entity_client_list_wildcard_with_filter():
    """Test that list() with workspace=ALL_WORKSPACES and filters works correctly."""

    class TestEntity(EntityBase):
        field_1: str
        field_2: int

    # Mock the entities API
    mock_api = Mock()
    mock_api.list = AsyncMock()
    now = datetime.now()
    mock_api.list.return_value = EntitiesPage(
        data=[
            Entity(
                entity_type="test_entity",
                name="test-1",
                workspace="workspace-1",
                id="id-1",
                created_at=now,
                updated_at=now,
                db_version=1,
                data={"field_1": "value", "field_2": 42},
            ),
        ],
        pagination=PaginationData(page=1, page_size=100, total_pages=1, total_results=1, current_page_size=1),
    )

    client = EntityClient(mock_api)

    # Call list with workspace=ALL_WORKSPACES and filter
    result = await client.list(TestEntity, workspace=ALL_WORKSPACES, filter_obj={"field_1": "value"})

    # Verify that the API was called with "*" wildcard
    mock_api.list.assert_called_once()
    call_args = mock_api.list.call_args
    assert call_args.args[0] == "test_entity"
    assert call_args.kwargs["workspace"] == ALL_WORKSPACES
    # Verify search filter was converted properly
    import json

    filter_dict = json.loads(call_args.kwargs["filter"])
    assert filter_dict == {"data.field_1": "value"}

    # Verify result
    assert len(result.data) == 1
    assert result.data[0].field_1 == "value"
    assert result.data[0].field_2 == 42


@pytest.mark.asyncio
async def test_entity_client_list_wildcard_with_pagination():
    """Test that list() with workspace=ALL_WORKSPACES and pagination params works correctly."""

    class TestEntity(EntityBase):
        field_1: str

    # Mock the entities API
    mock_api = Mock()
    mock_api.list = AsyncMock()
    mock_api.list.return_value = EntitiesPage(
        data=[],
        pagination=PaginationData(page=2, page_size=50, total_pages=3, total_results=150, current_page_size=0),
    )

    client = EntityClient(mock_api)

    # Call list with workspace=ALL_WORKSPACES and pagination
    result = await client.list(TestEntity, workspace=ALL_WORKSPACES, page=2, page_size=50)

    # Verify that the API was called with correct params
    mock_api.list.assert_called_once()
    call_args = mock_api.list.call_args
    assert call_args.kwargs["workspace"] == ALL_WORKSPACES
    assert call_args.kwargs["page"] == 2
    assert call_args.kwargs["page_size"] == 50

    # Verify pagination info
    assert result.pagination.page == 2
    assert result.pagination.page_size == 50
    assert result.pagination.total_pages == 3
    assert result.pagination.total_results == 150


@pytest.mark.asyncio
async def test_entity_client_list_rejects_combined_filter_operation_and_filter_str():
    """Supplying both filter_operation and filter_str raises rather than silently dropping one."""
    from nmp.common.api.filter import ComparisonOperation, FilterOperator

    class TestEntity(EntityBase):
        field_1: str

    mock_api = Mock()
    mock_api.list = AsyncMock()
    client = EntityClient(mock_api)

    op = ComparisonOperation(operator=FilterOperator.EQ, field="field_1", value="value")
    with pytest.raises(ValueError, match="filter_operation"):
        await client.list(TestEntity, filter_operation=op, filter_str='{"field_1":"value"}')

    mock_api.list.assert_not_called()


@pytest.mark.asyncio
async def test_entity_client_list_rejects_search_kwarg():
    """The legacy `search` alias is gone — passing it must be a TypeError."""

    class TestEntity(EntityBase):
        field_1: str

    mock_api = Mock()
    mock_api.list = AsyncMock()
    client = EntityClient(mock_api)

    with pytest.raises(TypeError):
        await client.list(TestEntity, search='{"field_1":"value"}')  # type: ignore[call-arg]


# ============================================================================
# DatetimeFilter Tests
# ============================================================================


class TestDatetimeFilter:
    """Tests for DatetimeFilter with alias support."""

    def test_accepts_gte_without_dollar(self):
        """Test that DatetimeFilter accepts 'gte' (without $) as input."""
        dt = datetime(2025, 1, 1, 0, 0, 0)
        f = DatetimeFilter(gte=dt)
        assert f.gte == dt

    def test_accepts_gte_with_dollar(self):
        """Test that DatetimeFilter accepts '$gte' (with $) as input."""
        dt = datetime(2025, 1, 1, 0, 0, 0)
        f = DatetimeFilter(**{"$gte": dt})
        assert f.gte == dt

    def test_accepts_lte_without_dollar(self):
        """Test that DatetimeFilter accepts 'lte' (without $) as input."""
        dt = datetime(2025, 12, 31, 23, 59, 59)
        f = DatetimeFilter(lte=dt)
        assert f.lte == dt

    def test_accepts_lte_with_dollar(self):
        """Test that DatetimeFilter accepts '$lte' (with $) as input."""
        dt = datetime(2025, 12, 31, 23, 59, 59)
        f = DatetimeFilter(**{"$lte": dt})
        assert f.lte == dt

    def test_model_dump_outputs_dollar_prefix(self):
        """Test that model_dump outputs $gte/$lte with by_alias=True."""
        dt_start = datetime(2025, 1, 1, 0, 0, 0)
        dt_end = datetime(2025, 12, 31, 23, 59, 59)
        f = DatetimeFilter(gte=dt_start, lte=dt_end)
        result = f.model_dump(exclude_none=True, by_alias=True, mode="json")

        assert "$gte" in result
        assert "$lte" in result
        assert "gte" not in result
        assert "lte" not in result
        assert result["$gte"] == dt_start.isoformat()
        assert result["$lte"] == dt_end.isoformat()

    def test_model_dump_json_serializes_datetime(self):
        """Test that mode='json' serializes datetime to ISO string."""
        dt = datetime(2025, 1, 1, 0, 0, 0)
        f = DatetimeFilter(gte=dt)
        result = f.model_dump(exclude_none=True, by_alias=True, mode="json")

        # Result should be JSON-serializable (datetime as string)
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        assert parsed["$gte"] == dt.isoformat()

    def test_accepts_both_gte_and_lte(self):
        """Test that DatetimeFilter accepts both fields together."""
        dt_start = datetime(2025, 1, 1, 0, 0, 0)
        dt_end = datetime(2025, 12, 31, 23, 59, 59)
        f = DatetimeFilter(gte=dt_start, lte=dt_end)
        assert f.gte == dt_start
        assert f.lte == dt_end

    def test_handles_timezone_aware_datetime(self):
        """Test that timezone-aware datetimes are handled correctly."""
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        f = DatetimeFilter(gte=dt)
        result = f.model_dump(exclude_none=True, by_alias=True, mode="json")
        # Pydantic serializes UTC as "Z" suffix instead of "+00:00"
        assert result["$gte"] in (dt.isoformat(), "2025-01-01T00:00:00Z")


# ============================================================================
# StringFilter Tests
# ============================================================================


class TestStringFilter:
    """Tests for StringFilter with alias support."""

    def test_accepts_eq_without_dollar(self):
        """Test that StringFilter accepts 'eq' (without $) as input."""
        f = StringFilter(eq="value")
        assert f.eq == "value"

    def test_accepts_eq_with_dollar(self):
        """Test that StringFilter accepts '$eq' (with $) as input."""
        f = StringFilter(**{"$eq": "value"})
        assert f.eq == "value"

    def test_accepts_like_without_dollar(self):
        """Test that StringFilter accepts 'like' (without $) as input."""
        f = StringFilter(like="%pattern%")
        assert f.like == "%pattern%"

    def test_accepts_like_with_dollar(self):
        """Test that StringFilter accepts '$like' (with $) as input."""
        f = StringFilter(**{"$like": "%pattern%"})
        assert f.like == "%pattern%"

    def test_accepts_in_without_dollar(self):
        """Test that StringFilter accepts 'in_' (without $) as input."""
        f = StringFilter(in_=["a", "b"])
        assert f.in_ == ["a", "b"]

    def test_accepts_in_with_dollar(self):
        """Test that StringFilter accepts '$in' (with $) as input."""
        f = StringFilter(**{"$in": ["a", "b"]})
        assert f.in_ == ["a", "b"]

    def test_accepts_nin_without_dollar(self):
        """Test that StringFilter accepts 'nin' (without $) as input."""
        f = StringFilter(nin=["x", "y"])
        assert f.nin == ["x", "y"]

    def test_accepts_nin_with_dollar(self):
        """Test that StringFilter accepts '$nin' (with $) as input."""
        f = StringFilter(**{"$nin": ["x", "y"]})
        assert f.nin == ["x", "y"]

    def test_model_dump_outputs_dollar_prefix(self):
        """Test that model_dump outputs $eq/$like/$in/$nin with by_alias=True."""
        f = StringFilter(eq="a", like="%b%", in_=["c", "d"], nin=["e"])
        result = f.model_dump(exclude_none=True, by_alias=True, mode="json")

        assert "$eq" in result
        assert "$like" in result
        assert "$in" in result
        assert "$nin" in result
        assert "eq" not in result
        assert "like" not in result
        assert "in_" not in result
        assert "nin" not in result
        assert result["$eq"] == "a"
        assert result["$like"] == "%b%"
        assert result["$in"] == ["c", "d"]
        assert result["$nin"] == ["e"]

    def test_model_dump_json_serializable(self):
        """Test that model_dump output is JSON-serializable."""
        f = StringFilter(eq="value", in_=["a", "b"])
        result = f.model_dump(exclude_none=True, by_alias=True, mode="json")

        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        assert parsed["$eq"] == "value"
        assert parsed["$in"] == ["a", "b"]

    def test_accepts_multiple_operators(self):
        """Test that StringFilter accepts several operators together."""
        f = StringFilter(eq="a", like="%b%")
        assert f.eq == "a"
        assert f.like == "%b%"


class TestConvertFilterToSearch:
    """Tests for _convert_filter_obj_to_filter_str function."""

    def test_base_fields_no_prefix(self):
        """Test that base fields (created_at, updated_at, etc.) don't get data. prefix."""
        filter_obj = {"created_at": {"$gte": "2025-01-01"}, "name": "test"}
        result = _convert_filter_obj_to_filter_str(filter_obj)

        assert "created_at" in result
        assert "name" in result
        assert "data.created_at" not in result
        assert "data.name" not in result

    def test_non_base_fields_get_data_prefix(self):
        """Test that non-base fields get data. prefix."""
        filter_obj = {"custom_field": "value"}
        result = _convert_filter_obj_to_filter_str(filter_obj)

        assert "data.custom_field" in result
        assert result["data.custom_field"] == "value"

    def test_preserves_nested_dict_structure(self):
        """Test that nested dict values are preserved."""
        filter_obj = {"created_at": {"$gte": "2025-01-01", "$lte": "2025-12-31"}}
        result = _convert_filter_obj_to_filter_str(filter_obj)

        assert result["created_at"] == {"$gte": "2025-01-01", "$lte": "2025-12-31"}

    def test_mixed_simple_and_nested_filters(self):
        """Test filter with both simple values and nested dicts."""
        filter_obj = {
            "name": "test-name",
            "created_at": {"$gte": "2025-01-01"},
            "workspace": "test-workspace",
        }
        result = _convert_filter_obj_to_filter_str(filter_obj)

        assert result["name"] == "test-name"
        assert result["workspace"] == "test-workspace"
        assert result["created_at"]["$gte"] == "2025-01-01"


@pytest.mark.asyncio
async def test_entity_client_list_with_datetime_filter():
    """Test that list() correctly passes datetime filters to the API search parameter."""

    class TestEntity(EntityBase):
        field_1: str

    # Mock the entities API - return empty page since we're only testing filter parsing
    mock_api = Mock()
    mock_api.list = AsyncMock()
    mock_api.list.return_value = EntitiesPage(
        data=[],
        pagination=PaginationData(page=1, page_size=100, total_pages=0, total_results=0, current_page_size=0),
    )

    client = EntityClient(mock_api)

    # Call list with datetime filter (already in $ format, as would come from filters.py)
    dt_start = "2025-01-01T00:00:00"
    dt_end = "2025-12-31T23:59:59"
    await client.list(
        TestEntity,
        workspace="test-workspace",
        filter_obj={"created_at": {"$gte": dt_start, "$lte": dt_end}},
    )

    # Verify that the API was called with the correct search string
    mock_api.list.assert_called_once()
    call_args = mock_api.list.call_args
    filter_str = call_args.kwargs["filter"]
    filter_dict = json.loads(filter_str)

    # Verify datetime filter was passed through correctly
    assert "created_at" in filter_dict
    assert filter_dict["created_at"]["$gte"] == dt_start
    assert filter_dict["created_at"]["$lte"] == dt_end


class NestedModel(BaseModel):
    """A nested model to test PrivateAttr deserialization."""

    user_id: str
    email: Optional[str] = None


def test_convert_api_entity_to_model_private_attr_basemodel():
    """Test that PrivateAttr with BaseModel type is properly deserialized."""

    class TestEntity(EntityBase):
        source: str
        _nested: Optional[NestedModel] = PrivateAttr(default=None)

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={
                "source": "test-source",
                "_nested": {"user_id": "user-123", "email": "test@example.com"},
            },
        ),
        TestEntity,
    )

    assert result.source == "test-source"
    # Verify the nested model is properly deserialized, not a raw dict
    assert result._nested is not None
    assert isinstance(result._nested, NestedModel)
    assert result._nested.user_id == "user-123"
    assert result._nested.email == "test@example.com"


def test_convert_api_entity_to_model_private_attr_list():
    """Test that PrivateAttr with List type is properly deserialized."""

    class TestEntity(EntityBase):
        source: str
        _tags: List[str] = PrivateAttr(default_factory=list)

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={
                "source": "test-source",
                "_tags": ["tag1", "tag2", "tag3"],
            },
        ),
        TestEntity,
    )

    assert result._tags == ["tag1", "tag2", "tag3"]
    assert isinstance(result._tags, list)


def test_convert_api_entity_to_model_private_attr_dict():
    """Test that PrivateAttr with Dict type is properly deserialized."""

    class TestEntity(EntityBase):
        source: str
        _metadata: Optional[Dict[str, Any]] = PrivateAttr(default=None)

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={
                "source": "test-source",
                "_metadata": {"key1": "value1", "nested": {"a": 1}},
            },
        ),
        TestEntity,
    )

    assert result._metadata == {"key1": "value1", "nested": {"a": 1}}
    assert isinstance(result._metadata, dict)


def test_convert_api_entity_to_model_private_attr_simple_types():
    """Test that PrivateAttr with simple types (int, bool) are properly deserialized."""

    class TestEntity(EntityBase):
        source: str
        _count: int = PrivateAttr(default=0)
        _enabled: bool = PrivateAttr(default=False)

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={
                "source": "test-source",
                "_count": 42,
                "_enabled": True,
            },
        ),
        TestEntity,
    )

    assert result._count == 42
    assert isinstance(result._count, int)
    assert result._enabled is True
    assert isinstance(result._enabled, bool)


def test_convert_api_entity_to_model_private_attr_none_value():
    """Test that PrivateAttr with None value is handled correctly."""

    class TestEntity(EntityBase):
        source: str
        _nested: Optional[NestedModel] = PrivateAttr(default=None)

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={
                "source": "test-source",
                "_nested": None,
            },
        ),
        TestEntity,
    )

    assert result._nested is None


def test_convert_api_entity_to_model_private_attr_missing():
    """Test that missing PrivateAttr in data uses the default value."""

    class TestEntity(EntityBase):
        source: str
        _nested: Optional[NestedModel] = PrivateAttr(default=None)
        _count: int = PrivateAttr(default=99)

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,
            data={
                "source": "test-source",
                # _nested and _count not in data
            },
        ),
        TestEntity,
    )

    # Should use defaults since not in data
    assert result._nested is None
    assert result._count == 99


def test_convert_api_entity_to_model_sets_db_version():
    """Test that version from API entity is set in the model."""

    class TestEntity(EntityBase):
        field_1: str

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=5,  # Version from API
            data={"field_1": "test"},
        ),
        TestEntity,
    )
    assert result._db_version == 5
    assert result.db_version == 5


def test_convert_api_entity_to_model_version_defaults_to_one():
    """Test that version defaults to 1 when not set in API entity."""

    class TestEntity(EntityBase):
        field_1: str

    now = datetime.now()
    entity_client = EntityClient(Mock())
    result = entity_client._convert_api_entity_to_model(
        Entity(
            entity_type="test",
            name="test",
            workspace="test",
            id="123",
            created_at=now,
            updated_at=now,
            db_version=1,  # Default version
            data={"field_1": "test"},
        ),
        TestEntity,
    )
    assert result._db_version == 1
    assert result.db_version == 1


def test_entity_base_db_version_defaults_to_one_for_new_entity():
    """Test that db_version property returns 1 for new entities."""

    class TestEntity(EntityBase):
        field_1: str

    entity = TestEntity(name="test", workspace="test", field_1="value")
    # _db_version defaults to 1 for new entities
    assert entity._db_version == 1
    # db_version property should return 1
    assert entity.db_version == 1


@pytest.mark.asyncio
async def test_update_with_automatic_version_check():
    """Test update automatically includes db_version for optimistic locking when entity was fetched."""

    class TestEntity(EntityBase):
        field_1: str

    now = datetime.now()
    mock_api = Mock()
    mock_api.get_entity_by_name = AsyncMock()
    mock_api.update_entity_by_name = AsyncMock()

    # Mock get returns entity with version 2
    existing_entity = Entity(
        entity_type="test_entity",
        name="test-entity",
        workspace="test-workspace",
        id="123",
        created_at=now,
        updated_at=now,
        db_version=2,
        data={"field_1": "old_value"},
    )
    mock_api.get_entity_by_name.return_value = existing_entity

    # Mock update returns updated entity with version 3
    updated_entity = Entity(
        entity_type="test_entity",
        name="test-entity",
        workspace="test-workspace",
        id="123",
        created_at=now,
        updated_at=now,
        db_version=3,  # Version incremented after update
        data={"field_1": "new_value"},
    )
    mock_api.update_entity_by_name.return_value = updated_entity

    client = EntityClient(mock_api)
    # Get entity (db_version automatically populated)
    entity = await client.get(TestEntity, "test-entity", workspace="test-workspace")
    # Modify entity
    entity.field_1 = "new_value"
    # Update (db_version automatically included)
    result = await client.update(entity)

    # Verify get was called to fetch existing entity
    mock_api.get_entity_by_name.assert_called_once()
    # Verify update was called with expected_db_version in request body (not headers)
    mock_api.update_entity_by_name.assert_called_once()
    call_kwargs = mock_api.update_entity_by_name.call_args[1]
    assert call_kwargs["expected_db_version"] == 2
    # Verify result has updated field
    assert result.field_1 == "new_value"
    assert result.db_version == 3


@pytest.mark.asyncio
async def test_update_version_mismatch_raises_conflict():
    """Test update raises EntityConflictError when db_version doesn't match (entity was modified)."""

    class TestEntity(EntityBase):
        field_1: str

    from nemo_platform import ConflictError

    now = datetime.now()
    mock_api = Mock()
    mock_api.get_entity_by_name = AsyncMock()
    mock_api.update_entity_by_name = AsyncMock()

    # Mock get returns entity with version 2
    existing_entity = Entity(
        entity_type="test_entity",
        name="test-entity",
        workspace="test-workspace",
        id="123",
        created_at=now,
        updated_at=now,
        db_version=2,
        data={"field_1": "old_value"},
    )
    mock_api.get_entity_by_name.return_value = existing_entity

    # Mock update_entity_by_name to raise ConflictError (server-side version check fails)
    # This simulates another request modified the entity (version is now 3, not 2)
    mock_response = Mock()
    mock_response.status_code = 409
    mock_api.update_entity_by_name.side_effect = ConflictError(
        message="Entity 'test-entity' of type 'test_entity' in workspace 'test-workspace' was modified by another request. Expected version 2, but current version is 3. Please refetch and retry.",
        response=mock_response,
        body=None,
    )

    client = EntityClient(mock_api)
    # Get entity (db_version automatically populated as 2)
    entity = await client.get(TestEntity, "test-entity", workspace="test-workspace")
    # Modify entity
    entity.field_1 = "new_value"
    # Update should fail because version changed
    with pytest.raises(EntityConflictError) as exc_info:
        await client.update(entity)

    # Verify error message mentions version mismatch
    assert "modified" in str(exc_info.value).lower() or "version" in str(exc_info.value).lower()
    # Verify update was called with expected_db_version in request body (not headers)
    mock_api.update_entity_by_name.assert_called_once()
    call_kwargs = mock_api.update_entity_by_name.call_args[1]
    assert call_kwargs["expected_db_version"] == 2


@pytest.mark.asyncio
async def test_update_without_version_works():
    """Test update works for entities created directly (not fetched), using default db_version=1."""

    class TestEntity(EntityBase):
        field_1: str

    now = datetime.now()
    mock_api = Mock()
    mock_api.update_entity_by_name = AsyncMock()

    # Mock update returns updated entity
    updated_entity = Entity(
        entity_type="test_entity",
        name="test-entity",
        workspace="test-workspace",
        id="123",
        created_at=now,
        updated_at=now,
        db_version=1,  # First version
        data={"field_1": "new_value"},
    )
    mock_api.update_entity_by_name.return_value = updated_entity

    client = EntityClient(mock_api)
    # Create entity directly (_db_version defaults to 1)
    entity = TestEntity(
        name="test-entity",
        workspace="test-workspace",
        field_1="old_value",
    )
    # Modify entity
    entity.field_1 = "new_value"
    # Update should work with default db_version=1
    result = await client.update(entity)

    # Verify update was called with expected_db_version=1 (default for new entities)
    mock_api.update_entity_by_name.assert_called_once()
    call_kwargs = mock_api.update_entity_by_name.call_args[1]
    # expected_db_version should be 1 (default for new entities)
    assert call_kwargs.get("expected_db_version") == 1
    # Verify result has updated field
    assert result.field_1 == "new_value"


class _EntityWithAuthContext(EntityBase):
    source: str
    _auth_context: Optional[AuthContext] = PrivateAttr(default=None)

    @computed_field
    @property
    def auth_context(self) -> Optional[AuthContext]:
        return self._auth_context


def _make_entity_with_auth_context(now: datetime) -> Entity:
    return Entity(
        entity_type="test",
        name="test",
        workspace="test",
        id="123",
        created_at=now,
        updated_at=now,
        db_version=1,
        data={
            "source": "test-source",
            "_auth_context": {
                "principal_id": "creator@example.com",
                "principal_email": "creator@example.com",
                "principal_groups": ["team-alpha"],
            },
        },
    )


def _entity_client_with_headers(headers: dict[str, str]) -> EntityClient:
    mock_api = Mock()
    mock_api._client.default_headers = headers
    return EntityClient(mock_api)


class TestAuthContextSanitization:
    def test_sanitizes_auth_context_for_regular_user(self):
        now = datetime.now()
        client = _entity_client_with_headers({"X-NMP-Principal-Id": "user@example.com"})

        result = client._convert_api_entity_to_model(
            _make_entity_with_auth_context(now),
            _EntityWithAuthContext,
        )

        assert result.auth_context is None

    def test_keeps_auth_context_for_service_principal(self):
        now = datetime.now()
        client = _entity_client_with_headers({"X-NMP-Principal-Id": "service:models-controller"})

        result = client._convert_api_entity_to_model(
            _make_entity_with_auth_context(now),
            _EntityWithAuthContext,
        )

        assert result.auth_context is not None
        assert result.auth_context.principal_id == "creator@example.com"
        assert result.auth_context.principal_email == "creator@example.com"
        assert result.auth_context.principal_groups == ["team-alpha"]

    def test_sanitizes_auth_context_when_no_principal_header(self):
        now = datetime.now()
        client = _entity_client_with_headers({})

        result = client._convert_api_entity_to_model(
            _make_entity_with_auth_context(now),
            _EntityWithAuthContext,
        )

        assert result.auth_context is None

    def test_no_effect_on_entity_without_auth_context(self):
        class EntityNoAuth(EntityBase):
            source: str

        now = datetime.now()
        client = _entity_client_with_headers({"X-NMP-Principal-Id": "user@example.com"})

        result = client._convert_api_entity_to_model(
            Entity(
                entity_type="test",
                name="test",
                workspace="test",
                id="123",
                created_at=now,
                updated_at=now,
                db_version=1,
                data={"source": "test-source"},
            ),
            EntityNoAuth,
        )

        assert result.source == "test-source"
