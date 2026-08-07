import hashlib
import json
from typing import Any

from flask import current_app
from redis import RedisError

from chargemate.stations.providers.open_charge_map import (
    ExternalStationProviderError,
    fetch_open_charge_map_stations,
)
from chargemate.stations.schemas import ExternalStationSearchQuery


EXTERNAL_CACHE_PREFIX = "chargemate:stations:external"
EXTERNAL_CACHE_TTL_SECONDS = 300


def find_external_stations(
    query: ExternalStationSearchQuery,
) -> list[dict[str, Any]]:
    """Return cached or freshly fetched Open Charge Map stations."""

    cache_key = _cache_key(query)
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    api_key = current_app.config.get("OPEN_CHARGE_MAP_API_KEY")
    if not api_key:
        raise ExternalStationProviderError

    stations = fetch_open_charge_map_stations(query, api_key)
    _write_cache(cache_key, stations)
    return stations


def _cache_key(query: ExternalStationSearchQuery) -> str:
    canonical_query = json.dumps(
        query.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical_query.encode("utf-8")).hexdigest()
    return f"{EXTERNAL_CACHE_PREFIX}:{digest}"


def _read_cache(cache_key: str) -> list[dict[str, Any]] | None:
    if current_app.testing:
        return None
    try:
        cached = current_app.extensions["redis"].get(cache_key)
        if cached is None:
            return None
        payload = json.loads(cached)
        return payload if isinstance(payload, list) else None
    except (RedisError, json.JSONDecodeError, TypeError):
        current_app.logger.warning(
            "External station cache read failed.",
            exc_info=True,
        )
        return None


def _write_cache(cache_key: str, stations: list[dict[str, Any]]) -> None:
    if current_app.testing:
        return
    try:
        current_app.extensions["redis"].setex(
            cache_key,
            EXTERNAL_CACHE_TTL_SECONDS,
            json.dumps(stations, separators=(",", ":"), sort_keys=True),
        )
    except RedisError:
        current_app.logger.warning(
            "External station cache write failed.",
            exc_info=True,
        )
