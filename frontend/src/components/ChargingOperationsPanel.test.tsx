import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, describe, expect, it, vi} from "vitest";
import {
  completeChargingSession,
  listChargingOperations,
  startChargingSession,
} from "../api/chargingSessions";
import type {
  ChargingOperation,
  ChargingOperationPage,
  ChargingSessionResponse,
} from "../types/chargingSession";
import {ChargingOperationsPanel} from "./ChargingOperationsPanel";

vi.mock("../api/chargingSessions", () => ({
  completeChargingSession: vi.fn(),
  listChargingOperations: vi.fn(),
  startChargingSession: vi.fn(),
}));

describe("ChargingOperationsPanel", () => {
  beforeEach(() => {
    vi.mocked(completeChargingSession).mockReset();
    vi.mocked(listChargingOperations).mockReset();
    vi.mocked(startChargingSession).mockReset();
  });

  it("rejects an empty meter and submits a valid reading with the booking version", async () => {
    const operation = confirmedOperation();
    vi.mocked(listChargingOperations).mockResolvedValue(page(operation));
    vi.mocked(startChargingSession).mockResolvedValue(
      {} as ChargingSessionResponse,
    );

    const user = userEvent.setup();
    render(<ChargingOperationsPanel open onClose={vi.fn()} />);

    await screen.findByText("Manual Test User");
    await user.click(screen.getByRole("button", {name: "Start charging"}));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a valid non-negative cumulative meter reading",
    );
    expect(startChargingSession).not.toHaveBeenCalled();

    await user.type(
      screen.getByLabelText("Starting cumulative meter (kWh)"),
      "1200.125",
    );
    await user.click(screen.getByRole("button", {name: "Start charging"}));

    await waitFor(() => {
      expect(startChargingSession).toHaveBeenCalledWith(
        operation.booking.id,
        operation.booking.version,
        1200.125,
      );
    });
  });
});

function confirmedOperation(): ChargingOperation {
  return {
    booking: {
      id: "booking-1",
      status: "confirmed",
      version: 4,
      starts_at: "2026-08-09T10:00:00+00:00",
      ends_at: "2026-08-09T11:00:00+00:00",
    },
    customer: {
      id: "user-1",
      full_name: "Manual Test User",
      email: "manual@example.com",
    },
    charge_point: {
      id: "point-1",
      code: "DC-01",
      connector_type: "ccs_2",
      max_power_kw: 60,
    },
    station: {
      id: "station-1",
      name: "ChargeMate Vijay Nagar",
      city: "Indore",
      state: "Madhya Pradesh",
    },
    charging_session: null,
  };
}

function page(operation: ChargingOperation): ChargingOperationPage {
  return {
    operations: [operation],
    pagination: {page: 1, per_page: 20, total: 1, pages: 1},
  };
}
