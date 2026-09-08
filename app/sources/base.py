from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models import Filters, Listing

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
}


class SourceError(Exception):
    pass


class BaseSource:
    name = "base"

    async def search(self, client: httpx.AsyncClient, filters: Filters) -> list[Listing]:
        raise NotImplementedError

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(settings.request_timeout)
