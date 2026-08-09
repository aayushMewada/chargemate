import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {
  createOwnedStation,
  listOwnedStations,
  updateOwnedChargePoint,
  updateOwnedStation,
  updateOwnedStationStatus,
} from "../api/stations";
import {ApiError} from "../api/client";
import type {ManagedStation, OwnedStationResponse} from "../types/station";
import {StationAdminPanel} from "./StationAdminPanel";

vi.mock("../api/stations", () => ({
  createOwnedStation: vi.fn(),
  listOwnedStations: vi.fn(),
  updateOwnedChargePoint: vi.fn(),
  updateOwnedStation: vi.fn(),
  updateOwnedStationStatus: vi.fn(),
}));

describe("StationAdminPanel", () => {
  beforeEach(() => {
    vi.mocked(createOwnedStation).mockReset();
    vi.mocked(listOwnedStations).mockReset();
    vi.mocked(updateOwnedChargePoint).mockReset();
    vi.mocked(updateOwnedStation).mockReset();
    vi.mocked(updateOwnedStationStatus).mockReset();
  });

  it("keeps conflict feedback visible after refreshing stale station data", async () => {
    const original = station({name: "Original Station", status: "active", version: 1});
    const refreshed = station({name: "Updated in tab A", status: "maintenance", version: 2});
    vi.mocked(listOwnedStations)
      .mockResolvedValueOnce(page(original))
      .mockResolvedValueOnce(page(refreshed));
    vi.mocked(updateOwnedStationStatus).mockRejectedValue(
      new ApiError(
        409,
        "station_state_conflict",
        "The station data changed.",
      ),
    );

    const user = userEvent.setup();
    render(<StationAdminPanel open onClose={vi.fn()} />);

    await screen.findByText("Original Station");
    await user.selectOptions(screen.getByLabelText("Station status"), "maintenance");

    expect(await screen.findByText("Updated in tab A")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Fresh data has been loaded",
    );
    expect(updateOwnedStationStatus).toHaveBeenCalledWith(
      original.id,
      1,
      "maintenance",
    );
    expect(listOwnedStations).toHaveBeenCalledTimes(2);
  });
});

function station(
  changes: Partial<ManagedStation> = {},
): ManagedStation {
  return {
    id: "station-1",
    owner_id: "owner-1",
    name: "Test Station",
    description: null,
    address_line_1: "101 Test Road",
    address_line_2: null,
    city: "Indore",
    state: "Madhya Pradesh",
    postal_code: "452001",
    country_code: "IN",
    latitude: 22.7196,
    longitude: 75.8577,
    timezone: "Asia/Kolkata",
    phone: null,
    status: "draft",
    is_24_hours: true,
    version: 1,
    charge_points: [{
      id: "point-1",
      code: "DC-01",
      connector_type: "ccs_2",
      power_type: "dc",
      max_power_kw: 60,
      booking_fee: 50,
      is_bookable: true,
      status: "available",
      version: 1,
    }],
    created_at: "2026-08-09T10:00:00+00:00",
    ...changes,
  };
}

function page(item: ManagedStation): OwnedStationResponse {
  return {
    stations: [item],
    pagination: {page: 1, per_page: 20, total: 1, pages: 1},
  };
}
