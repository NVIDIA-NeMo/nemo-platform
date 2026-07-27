# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from nmp.common.auth.jwks import AsyncJWKSClient

JWKS_URI = "https://auth.example.test/jwks"


def _rsa_key_and_jwk(kid: str) -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, jwk


def _token(private_key: Any, *, kid: str | None) -> str:
    headers = {"kid": kid} if kid is not None else None
    return jwt.encode({"sub": "user"}, private_key, algorithm="RS256", headers=headers)


class JWKSResponder:
    def __init__(self, jwks_responses: list[dict[str, Any]]) -> None:
        self._jwks_responses = jwks_responses
        self.calls = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == JWKS_URI
        timeout = request.extensions["timeout"]
        assert all(value == 10.0 for value in timeout.values())
        self.calls += 1
        await asyncio.sleep(0.01)
        if len(self._jwks_responses) > 1:
            return httpx.Response(200, json=self._jwks_responses.pop(0), request=request)
        return httpx.Response(200, json=self._jwks_responses[0], request=request)


async def test_aclose_closes_owned_http_client() -> None:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    with patch("nmp.common.auth.jwks.DefaultAsyncHttpxClient", return_value=http_client):
        client = AsyncJWKSClient(JWKS_URI)

    await client.aclose()

    http_client.aclose.assert_awaited_once_with()


async def test_aclose_does_not_close_injected_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200)))
    close = AsyncMock()
    monkeypatch.setattr(http_client, "aclose", close)

    client = AsyncJWKSClient(JWKS_URI, http_client=http_client)
    await client.aclose()

    close.assert_not_awaited()
    await httpx.AsyncClient.aclose(http_client)


@pytest.mark.parametrize("bad_token", ["malformed-token", None])
async def test_cached_jwks_lookup_does_not_refresh_malformed_or_missing_kid_tokens(bad_token):
    private_key, jwk = _rsa_key_and_jwk("known-key")
    responder = JWKSResponder([{"keys": [jwk]}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http_client:
        client = AsyncJWKSClient(JWKS_URI, http_client=http_client)
        await client.get_signing_key_from_jwt(_token(private_key, kid="known-key"))

        token = bad_token if bad_token is not None else _token(private_key, kid=None)
        with pytest.raises(jwt.InvalidTokenError):
            await client.get_signing_key_from_jwt(token)

        assert responder.calls == 1


async def test_cached_unknown_kid_concurrent_refresh_uses_single_refreshed_jwks():
    known_private_key, known_jwk = _rsa_key_and_jwk("known-key")
    rotated_private_key, rotated_jwk = _rsa_key_and_jwk("rotated-key")
    responder = JWKSResponder([{"keys": [known_jwk]}, {"keys": [rotated_jwk]}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http_client:
        client = AsyncJWKSClient(JWKS_URI, http_client=http_client)
        await client.get_signing_key_from_jwt(_token(known_private_key, kid="known-key"))
        rotated_token = _token(rotated_private_key, kid="rotated-key")

        results = await asyncio.gather(*(client.get_signing_key_from_jwt(rotated_token) for _ in range(5)))

        assert [result.key_id for result in results] == ["rotated-key"] * 5
        assert responder.calls == 2


async def test_cached_unknown_kid_refresh_is_rate_limited():
    private_key, jwk = _rsa_key_and_jwk("known-key")
    responder = JWKSResponder([{"keys": [jwk]}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http_client:
        client = AsyncJWKSClient(JWKS_URI, http_client=http_client)
        await client.get_signing_key_from_jwt(_token(private_key, kid="known-key"))
        unknown_token = _token(private_key, kid="unknown-key")

        results = await asyncio.gather(
            *(client.get_signing_key_from_jwt(unknown_token) for _ in range(5)),
            return_exceptions=True,
        )

        assert all(isinstance(result, jwt.InvalidTokenError) for result in results)
        assert responder.calls == 2

        with pytest.raises(jwt.InvalidTokenError):
            await client.get_signing_key_from_jwt(unknown_token)

        assert responder.calls == 2
