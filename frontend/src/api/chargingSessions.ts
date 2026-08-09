import {requestJson} from "./client";
import type {
  ChargingOperationPage,
  ChargingSessionPage,
  ChargingSessionResponse,
  ChargingSessionStatus,
} from "../types/chargingSession";

export function listMyChargingSessions(
  status?: ChargingSessionStatus,
  page = 1,
): Promise<ChargingSessionPage> {
  const query = new URLSearchParams({page: String(page), per_page: "20"});
  if (status) query.set("status", status);
  return requestJson<ChargingSessionPage>(
    `/charging-sessions/me?${query.toString()}`,
    {authenticated: true},
  );
}

export function listChargingOperations(page = 1): Promise<ChargingOperationPage> {
  const query = new URLSearchParams({page: String(page), per_page: "20"});
  return requestJson<ChargingOperationPage>(
    `/charging-sessions/operations?${query.toString()}`,
    {authenticated: true},
  );
}

export async function startChargingSession(
  bookingId: string,
  bookingVersion: number,
  meterStartKwh: number,
): Promise<ChargingSessionResponse> {
  return requestJson<ChargingSessionResponse>("/charging-sessions", {
    method: "POST",
    authenticated: true,
    body: JSON.stringify({
      booking_id: bookingId,
      booking_version: bookingVersion,
      meter_start_kwh: meterStartKwh,
    }),
  });
}

export async function completeChargingSession(
  sessionId: string,
  version: number,
  meterEndKwh: number,
): Promise<ChargingSessionResponse> {
  return requestJson<ChargingSessionResponse>(
    `/charging-sessions/${sessionId}/complete`,
    {
      method: "POST",
      authenticated: true,
      body: JSON.stringify({version, meter_end_kwh: meterEndKwh}),
    },
  );
}
