from chargemate.stations.cache import (
    get_cached_station_search,
    invalidate_station_searches,
    store_station_search,
)
from chargemate.stations.schemas import StationSearchQuery


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, _ttl_seconds: int, value: str) -> None:
        self.values[key] = value

    def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value


def test_station_search_cache_round_trip(app, monkeypatch):
    fake_redis = FakeRedis()
    query = StationSearchQuery(city="Indore", page=1, per_page=20)
    payload = {"stations": [], "pagination": {"total": 0}}
    monkeypatch.setitem(app.config, "STATION_SEARCH_CACHE_ENABLED", True)
    monkeypatch.setitem(app.extensions, "redis", fake_redis)

    with app.app_context():
        cache_key, cached = get_cached_station_search(query)
        assert cache_key is not None
        assert cached is None

        store_station_search(cache_key, payload)
        repeated_key, cached = get_cached_station_search(query)

    assert repeated_key == cache_key
    assert cached == payload


def test_station_search_invalidation_advances_namespace(app, monkeypatch):
    fake_redis = FakeRedis()
    query = StationSearchQuery(city="Indore")
    payload = {"stations": [{"id": "old-result"}]}
    monkeypatch.setitem(app.config, "STATION_SEARCH_CACHE_ENABLED", True)
    monkeypatch.setitem(app.extensions, "redis", fake_redis)

    with app.app_context():
        old_key, _ = get_cached_station_search(query)
        store_station_search(old_key, payload)
        invalidate_station_searches()
        new_key, cached = get_cached_station_search(query)

    assert new_key != old_key
    assert cached is None
