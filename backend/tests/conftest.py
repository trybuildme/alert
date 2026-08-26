"""
Shared test fixtures.

- Blocks all external HTTP so the suite never touches the network
  (individual tests may override with their own MockTransport).
- Isolates the tile cache directory so tests never see entries written
  by the live server (or previous runs).
"""

import os
import shutil

# Must be set before app.core.config is imported anywhere.
os.environ["NOAH_TILE_CACHE_DIR"] = "/tmp/noah-test-cache"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.api import esri_proxy, elevation, gibs_proxy, search  # noqa: E402


def _deny(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, content=b"external http blocked in tests")


@pytest.fixture(scope="session", autouse=True)
def clean_cache_dir():
    shutil.rmtree("/tmp/noah-test-cache", ignore_errors=True)
    yield
    shutil.rmtree("/tmp/noah-test-cache", ignore_errors=True)


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    mock = httpx.MockTransport(_deny)
    monkeypatch.setattr(esri_proxy, "_client", httpx.AsyncClient(transport=mock))
    monkeypatch.setattr(search, "_client", httpx.AsyncClient(transport=mock))
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock))
    monkeypatch.setattr(elevation, "_client", httpx.AsyncClient(transport=mock))
