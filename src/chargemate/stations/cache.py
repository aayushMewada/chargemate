import hashlib
import json
from typing import Any

from flask import current_app
from redis import RedisError

from chargemate.stations.schemas import StationSearchQuery


CACHE_VERSION_KEY = "chargemate:stations:search:version"
CACHE_KEY_PREFIX = "chargemate:stations:search"
DEFAULT_CACHE_TTL_SECONDS = 60


def get_cached_station_search(
    query: StationSearchQuery,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return the versioned cache key and its decoded payload, if available."""

    if not _cache_is_enabled():
        return None, None

    redis_client = _redis_client()
    try:
        version = redis_client.get(CACHE_VERSION_KEY) or "0"
        cache_key = _build_cache_key(query, version)
        cached_value = redis_client.get(cache_key)
        if cached_value is None:
            return cache_key, None
        return cache_key, json.loads(cached_value)
    except (RedisError, json.JSONDecodeError, TypeError):
        current_app.logger.warning(
            "Station search cache read failed.",
            exc_info=True,
        )
        return None, None


def store_station_search(cache_key: str | None, payload: dict[str, Any]) -> None:
    """Store a search response briefly without affecting request success."""

    if cache_key is None or not _cache_is_enabled():
        return

    ttl_seconds = current_app.config.get(
        "STATION_SEARCH_CACHE_TTL_SECONDS",
        DEFAULT_CACHE_TTL_SECONDS,
    )
    try:
        _redis_client().setex(
            cache_key,
            ttl_seconds,
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
    except RedisError:
        current_app.logger.warning(
            "Station search cache write failed.",
            exc_info=True,
        )


def invalidate_station_searches() -> None:
    """Make all older search keys unreachable by advancing their version."""

    if not _cache_is_enabled():
        return

    try:
        _redis_client().incr(CACHE_VERSION_KEY)
    except RedisError:
        current_app.logger.warning(
            "Station search cache invalidation failed.",
            exc_info=True,
        )


def _build_cache_key(query: StationSearchQuery, version: str) -> str:
    canonical_query = json.dumps(
        query.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical_query.encode("utf-8")).hexdigest()
    return f"{CACHE_KEY_PREFIX}:v{version}:{digest}"


def _cache_is_enabled() -> bool:
    return current_app.config.get(
        "STATION_SEARCH_CACHE_ENABLED",
        not current_app.testing,
    )


def _redis_client():
    return current_app.extensions["redis"]
