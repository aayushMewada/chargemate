import {afterEach, describe, expect, it, vi} from "vitest";
import {searchManagedStations} from "./stations";


afterEach(() => {
  vi.unstubAllGlobals();
});

describe("station search requests", () => {
  it("rounds browser coordinates to the precision accepted by the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          stations: [],
          pagination: {page: 1, per_page: 100, total: 0, pages: 0},
        }),
        {
          status: 200,
          headers: {"Content-Type": "application/json"},
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await searchManagedStations({
      latitude: 19.281867899999998,
      longitude: 72.886660123456,
      radiusKm: 25,
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/stations?latitude=19.281868&longitude=72.886660&radius_km=25&per_page=100",
    );
  });
});
