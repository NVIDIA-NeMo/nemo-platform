# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for prompt API v2 endpoints."""

import pytest
from httpx import AsyncClient

BASE = "/apis/entities/v2/workspaces/default/prompts"


@pytest.mark.integration
@pytest.mark.asyncio
class TestPromptCRUD:
    """Test CRUD operations for the prompt endpoints."""

    async def test_create_prompt(self, client: AsyncClient, ctx):
        response = await client.post(
            BASE,
            json={
                "name": "my-prompt",
                "description": "A test prompt",
                "tags": ["rag", "system"],
                "template": "Answer in {{language}} using: {{context}}",
                "change_note": "Initial version",
            },
        )
        assert response.status_code == 201
        result = response.json()
        assert result["name"] == "my-prompt"
        assert result["workspace"] == "default"
        assert result["description"] == "A test prompt"
        assert result["tags"] == ["rag", "system"]
        assert result["version_count"] == 1
        assert result["current_version"] is not None
        assert result["current_version"]["version_number"] == 1
        assert result["current_version"]["template"] == "Answer in {{language}} using: {{context}}"
        assert result["current_version"]["variables"] == ["language", "context"]
        assert result["current_version"]["change_note"] == "Initial version"
        assert "id" in result
        assert "created_at" in result

    async def test_create_prompt_auto_name(self, client: AsyncClient, ctx):
        response = await client.post(BASE, json={"template": "Hello {{name}}"})
        assert response.status_code == 201
        result = response.json()
        assert result["name"].startswith("prompt-")
        assert result["current_version"]["template"] == "Hello {{name}}"

    async def test_create_prompt_with_model_params(self, client: AsyncClient, ctx):
        response = await client.post(
            BASE,
            json={
                "name": "param-prompt",
                "template": "Say {{thing}}",
                "model_params": {"temperature": 0.7, "max_tokens": 512, "top_p": 0.9},
            },
        )
        assert response.status_code == 201
        result = response.json()
        params = result["current_version"]["model_params"]
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 512
        assert params["top_p"] == 0.9

    async def test_create_duplicate_prompt_returns_409(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "dup-prompt", "template": "Hello"})
        response = await client.post(BASE, json={"name": "dup-prompt", "template": "Hello again"})
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    async def test_create_prompt_rejects_unknown_fields(self, client: AsyncClient, ctx):
        response = await client.post(BASE, json={"template": "Hi", "unknown_field": "value"})
        assert response.status_code == 422

    async def test_create_prompt_model_params_temperature_out_of_range(self, client: AsyncClient, ctx):
        response = await client.post(
            BASE,
            json={"template": "Hi", "model_params": {"temperature": 3.0}},
        )
        assert response.status_code == 422

    async def test_create_prompt_model_params_top_p_out_of_range(self, client: AsyncClient, ctx):
        response = await client.post(
            BASE,
            json={"template": "Hi", "model_params": {"top_p": 1.5}},
        )
        assert response.status_code == 422

    async def test_get_prompt(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "get-me", "template": "Retrieve {{this}}"})
        response = await client.get(f"{BASE}/get-me")
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "get-me"
        assert result["current_version"]["template"] == "Retrieve {{this}}"

    async def test_get_nonexistent_prompt_returns_404(self, client: AsyncClient, ctx):
        response = await client.get(f"{BASE}/does-not-exist")
        assert response.status_code == 404

    async def test_list_prompts(self, client: AsyncClient, ctx):
        for i in range(3):
            await client.post(BASE, json={"name": f"list-prompt-{i}", "template": f"Template {i}"})
        response = await client.get(BASE)
        assert response.status_code == 200
        result = response.json()
        assert result["pagination"]["total_results"] >= 3
        names = [p["name"] for p in result["data"]]
        for i in range(3):
            assert f"list-prompt-{i}" in names

    async def test_list_prompts_empty_workspace(self, client: AsyncClient, ctx):
        response = await client.get(BASE)
        assert response.status_code == 200
        result = response.json()
        assert result["data"] == []
        assert result["pagination"]["total_results"] == 0

    async def test_update_prompt_description(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "update-me", "template": "Hello", "description": "Old"})
        response = await client.put(f"{BASE}/update-me", json={"description": "New description"})
        assert response.status_code == 200
        result = response.json()
        assert result["description"] == "New description"

    async def test_update_prompt_tags(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "tag-me", "template": "Tag test", "tags": ["a", "b"]})
        response = await client.put(f"{BASE}/tag-me", json={"tags": ["c"]})
        assert response.status_code == 200
        assert response.json()["tags"] == ["c"]

    async def test_update_prompt_project_associate(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "proj-prompt", "template": "Hello"})
        response = await client.put(f"{BASE}/proj-prompt", json={"project": "my-project"})
        assert response.status_code == 200
        assert response.json()["project"] == "my-project"

    async def test_update_prompt_project_disassociate(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "disassoc-prompt", "template": "Hello", "project": "p1"})
        response = await client.put(f"{BASE}/disassoc-prompt", json={"project": None})
        assert response.status_code == 200
        assert response.json()["project"] is None

    async def test_update_prompt_omitting_project_preserves_it(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "keep-proj", "template": "Hello", "project": "kept"})
        response = await client.put(f"{BASE}/keep-proj", json={"description": "Updated"})
        assert response.status_code == 200
        assert response.json()["project"] == "kept"

    async def test_update_nonexistent_prompt_returns_404(self, client: AsyncClient, ctx):
        response = await client.put(f"{BASE}/ghost", json={"description": "Nope"})
        assert response.status_code == 404

    async def test_delete_prompt(self, client: AsyncClient, ctx):
        await client.post(BASE, json={"name": "del-me", "template": "Bye"})
        response = await client.delete(f"{BASE}/del-me")
        assert response.status_code == 200
        assert response.json()["deleted_count"] >= 1
        get_response = await client.get(f"{BASE}/del-me")
        assert get_response.status_code == 404

    async def test_delete_nonexistent_prompt_returns_404(self, client: AsyncClient, ctx):
        response = await client.delete(f"{BASE}/ghost-prompt")
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestPromptVersions:
    """Test versioning sub-routes for prompts."""

    async def _create_prompt(self, client: AsyncClient, name: str, template: str = "Template {{x}}") -> dict:
        response = await client.post(BASE, json={"name": name, "template": template})
        assert response.status_code == 201
        return response.json()

    async def test_create_version(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "v-prompt")
        response = await client.post(
            f"{BASE}/v-prompt/versions",
            json={"template": "Updated {{x}} template", "change_note": "Second version"},
        )
        assert response.status_code == 201
        result = response.json()
        assert result["version_number"] == 2
        assert result["template"] == "Updated {{x}} template"
        assert result["change_note"] == "Second version"
        assert result["prompt_name"] == "v-prompt"

    async def test_create_version_increments_version_count(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "count-prompt")
        await client.post(f"{BASE}/count-prompt/versions", json={"template": "v2"})
        await client.post(f"{BASE}/count-prompt/versions", json={"template": "v3"})
        response = await client.get(f"{BASE}/count-prompt")
        assert response.json()["version_count"] == 3

    async def test_create_version_updates_current_version(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "cur-prompt", "Original")
        await client.post(f"{BASE}/cur-prompt/versions", json={"template": "Updated"})
        response = await client.get(f"{BASE}/cur-prompt")
        assert response.json()["current_version"]["version_number"] == 2
        assert response.json()["current_version"]["template"] == "Updated"

    async def test_create_version_for_nonexistent_prompt_returns_404(self, client: AsyncClient, ctx):
        response = await client.post(f"{BASE}/no-such-prompt/versions", json={"template": "x"})
        assert response.status_code == 404

    async def test_list_versions(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "list-v-prompt")
        await client.post(f"{BASE}/list-v-prompt/versions", json={"template": "v2"})
        await client.post(f"{BASE}/list-v-prompt/versions", json={"template": "v3"})
        response = await client.get(f"{BASE}/list-v-prompt/versions")
        assert response.status_code == 200
        result = response.json()
        assert result["pagination"]["total_results"] == 3
        version_numbers = [v["version_number"] for v in result["data"]]
        assert version_numbers == [1, 2, 3]

    async def test_get_specific_version(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "specific-v-prompt", "Version one")
        await client.post(f"{BASE}/specific-v-prompt/versions", json={"template": "Version two"})
        response = await client.get(f"{BASE}/specific-v-prompt/versions/1")
        assert response.status_code == 200
        assert response.json()["version_number"] == 1
        assert response.json()["template"] == "Version one"

        response = await client.get(f"{BASE}/specific-v-prompt/versions/2")
        assert response.status_code == 200
        assert response.json()["version_number"] == 2
        assert response.json()["template"] == "Version two"

    async def test_get_nonexistent_version_returns_404(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "no-v-prompt")
        response = await client.get(f"{BASE}/no-v-prompt/versions/99")
        assert response.status_code == 404

    async def test_get_version_zero_returns_422(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "zero-v-prompt")
        response = await client.get(f"{BASE}/zero-v-prompt/versions/0")
        assert response.status_code == 422

    async def test_get_version_negative_returns_422(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "neg-v-prompt")
        response = await client.get(f"{BASE}/neg-v-prompt/versions/-1")
        assert response.status_code == 422

    async def test_version_variables_extracted(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "var-prompt", "Hello {{name}}, your score is {{score}}")
        response = await client.get(f"{BASE}/var-prompt/versions/1")
        assert response.status_code == 200
        assert response.json()["variables"] == ["name", "score"]

    async def test_version_model_params(self, client: AsyncClient, ctx):
        await self._create_prompt(client, "mp-prompt")
        response = await client.post(
            f"{BASE}/mp-prompt/versions",
            json={"template": "v2", "model_params": {"temperature": 0.5, "top_p": 0.8}},
        )
        assert response.status_code == 201
        params = response.json()["model_params"]
        assert params["temperature"] == 0.5
        assert params["top_p"] == 0.8
