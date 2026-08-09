import {requestJson} from "./client";
import type {
  ChargingSessionPage,
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
