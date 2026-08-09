import {expect, test, type Page} from "@playwright/test";


const DETECTED_LOCATION = {
  latitude: 19.281867899999998,
  longitude: 72.886660123456,
};

test.use({
  geolocation: DETECTED_LOCATION,
  permissions: ["geolocation"],
});

test("loads the station explorer", async ({page}) => {
  await mockStationSearches(page);
  await page.goto("/");

  await expect(
    page.getByRole("heading", {name: "Charging around you"}),
  ).toBeVisible();
  await expect(page.getByRole("button", {name: "Use my location"})).toBeVisible();
});

test("searches the detected location using API-safe coordinate precision", async ({page}) => {
  await mockStationSearches(page);
  await page.goto("/");

  const detectedSearch = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return (
      url.pathname === "/api/stations" &&
      url.searchParams.get("latitude") === "19.281868"
    );
  });

  await page.getByRole("button", {name: "Use my location"}).click();
  const request = await detectedSearch;
  const searchUrl = new URL(request.url());

  expect(searchUrl.searchParams.get("longitude")).toBe("72.886660");
  expect(searchUrl.searchParams.get("radius_km")).toBe("25");
  await expect(page.getByText("Borivali Test Station").first()).toBeVisible();
});

async function mockStationSearches(page: Page): Promise<void> {
  await page.route(
    (url) =>
      url.pathname === "/api/stations" ||
      url.pathname === "/api/stations/external",
    async (route) => {
      const url = new URL(route.request().url());

      if (url.pathname.endsWith("/external")) {
        await route.fulfill({
          json: {stations: [], source: "open_charge_map", bookable: false},
        });
        return;
      }

      const isDetectedLocation =
        url.searchParams.get("latitude") === "19.281868" &&
        url.searchParams.get("longitude") === "72.886660";

      await route.fulfill({
        json: {
          stations: isDetectedLocation ? [managedStation()] : [],
          pagination: {
            page: 1,
            per_page: 100,
            total: isDetectedLocation ? 1 : 0,
            pages: isDetectedLocation ? 1 : 0,
          },
        },
      });
    },
  );
}

function managedStation() {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    owner_id: "22222222-2222-4222-8222-222222222222",
    name: "Borivali Test Station",
    description: "A deterministic browser-test station.",
    address_line_1: "Borivali East",
    address_line_2: null,
    city: "Mumbai",
    state: "Maharashtra",
    postal_code: "400066",
    country_code: "IN",
    latitude: 19.281868,
    longitude: 72.88666,
    timezone: "Asia/Kolkata",
    phone: null,
    status: "active",
    is_24_hours: true,
    version: 1,
    distance_km: 0,
    created_at: "2026-08-10T00:00:00+00:00",
    charge_points: [
      {
        id: "33333333-3333-4333-8333-333333333333",
        code: "DC-E2E-01",
        connector_type: "ccs_2",
        power_type: "dc",
        max_power_kw: 60,
        booking_fee: 50,
        is_bookable: true,
        status: "available",
        version: 1,
      },
    ],
  };
}
