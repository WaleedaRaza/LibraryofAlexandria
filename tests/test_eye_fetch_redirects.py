"""The device PDF fetch must not follow a public link's redirect onto a private address (SSRF)."""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.routes import device_api
from app.services import reading_desk

PDF = b"%PDF-1.4 tiny"


def _client_factory(routes):
    real = httpx.AsyncClient

    def make(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda request: routes[str(request.url)]())
        return real(*args, **kwargs)
    return make


def _resolve(monkeypatch, table):
    def fake_getaddrinfo(host, port, type=None):
        return [(None, None, None, None, (table[host], port))]
    monkeypatch.setattr(reading_desk.socket, "getaddrinfo", fake_getaddrinfo)


def _run(coro):
    return asyncio.run(coro)


def test_redirect_to_metadata_server_is_refused(monkeypatch):
    _resolve(monkeypatch, {"books.example": "93.184.216.34", "metadata.google.internal": "169.254.169.254"})
    monkeypatch.setattr(device_api.httpx, "AsyncClient", _client_factory({
        "https://books.example/a.pdf": lambda: httpx.Response(302, headers={"location": "http://metadata.google.internal/computeMetadata/v1/"}),
    }))
    with pytest.raises(HTTPException) as caught:
        _run(device_api._stream_pdf("https://books.example/a.pdf", "a.pdf", untrusted=True))
    assert caught.value.status_code == 400


def test_public_redirects_are_still_followed(monkeypatch):
    _resolve(monkeypatch, {"books.example": "93.184.216.34", "cdn.example": "151.101.1.1"})
    monkeypatch.setattr(device_api.httpx, "AsyncClient", _client_factory({
        "https://books.example/a.pdf": lambda: httpx.Response(301, headers={"location": "https://cdn.example/a.pdf"}),
        "https://cdn.example/a.pdf": lambda: httpx.Response(200, content=PDF),
    }))
    response = _run(device_api._stream_pdf("https://books.example/a.pdf", "a.pdf", untrusted=True))
    assert response.status_code == 200


def test_ipv4_mapped_and_shared_addresses_are_private(monkeypatch):
    for address in ("::ffff:127.0.0.1", "100.64.0.1", "10.0.0.5"):
        _resolve(monkeypatch, {"h.example": address})
        with pytest.raises(ValueError):
            _run(reading_desk._validate_public_url("https://h.example/x.pdf"))
