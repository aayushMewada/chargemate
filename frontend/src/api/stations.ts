import {getJson, requestJson} from "./client";
import type {
  ChargePoint,
  ChargePointUpdateResponse,
  Coordinates,
  ExternalStation,
  ExternalStationResponse,
  ManagedStation,
  ManagedStationDetailResponse,
  ManagedStationResponse,
  OwnedStationResponse,
  StationMarker,
  StationCreateInput,
} from "../types/station";

export type StationStatus = "draft" | "active" | "inactive" | "maintenance";
export type ChargePointStatus =
  | "available"
  | "out_of_service"
  | "maintenance"
  | "retired";

export type StationUpdateChanges = Partial<{
  name: string;
  description: string | null;
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  country_code: string;
  latitude: number;
  longitude: number;
  timezone: string;
  phone: string | null;
  is_24_hours: boolean;
  status: StationStatus;
}>;

export type ChargePointUpdateChanges = Partial<{
  max_power_kw: number;
  booking_fee: number;
  is_bookable: boolean;
  status: ChargePointStatus;
}>;

export type StationSearch = Coordinates & {
  radiusKm: number;
};

export async function searchManagedStations(
  search: StationSearch,
  signal?: AbortSignal,
): Promise<StationMarker[]> {
  const query = stationQuery(search);
  query.set("per_page", "100");
  const response = await getJson<ManagedStationResponse>(
    `/stations?${query.toString()}`,
    signal,
  );
  return response.stations.map(toManagedMarker);
}

export async function searchExternalStations(
  search: StationSearch,
  signal?: AbortSignal,
): Promise<StationMarker[]> {
  const query = stationQuery(search);
  query.set("max_results", "100");
  const response = await getJson<ExternalStationResponse>(
    `/stations/external?${query.toString()}`,
    signal,
  );
  return response.stations.map(toExternalMarker);
}

export async function getManagedStation(
  stationId: string,
  signal?: AbortSignal,
): Promise<ManagedStation> {
  const response = await getJson<ManagedStationDetailResponse>(
    `/stations/${stationId}`,
    signal,
  );
  return response.station;
}

export function listOwnedStations(page = 1): Promise<OwnedStationResponse> {
  const query = new URLSearchParams({page: String(page), per_page: "20"});
  return requestJson<OwnedStationResponse>(`/stations/mine?${query.toString()}`, {
    authenticated: true,
  });
}

export async function createOwnedStation(
  input: StationCreateInput,
): Promise<ManagedStation> {
  const response = await requestJson<ManagedStationDetailResponse>("/stations", {
    method: "POST",
    authenticated: true,
    body: JSON.stringify(input),
  });
  return response.station;
}

export async function updateOwnedStationStatus(
  stationId: string,
  version: number,
  status: StationStatus,
): Promise<ManagedStation> {
  return updateOwnedStation(stationId, version, {status});
}

export async function updateOwnedStation(
  stationId: string,
  version: number,
  changes: StationUpdateChanges,
): Promise<ManagedStation> {
  const response = await requestJson<ManagedStationDetailResponse>(
    `/stations/${stationId}`,
    {
      method: "PATCH",
      authenticated: true,
      body: JSON.stringify({version, ...changes}),
    },
  );
  return response.station;
}

export async function updateOwnedChargePoint(
  stationId: string,
  chargePointId: string,
  version: number,
  changes: ChargePointUpdateChanges,
): Promise<ChargePoint> {
  const response = await requestJson<ChargePointUpdateResponse>(
    `/stations/${stationId}/charge-points/${chargePointId}`,
    {
      method: "PATCH",
      authenticated: true,
      body: JSON.stringify({version, ...changes}),
    },
  );
  return response.charge_point;
}

function stationQuery(search: StationSearch): URLSearchParams {
  return new URLSearchParams({
    // Browser geolocation commonly returns 12-15 decimal places, while the
    // API and PostgreSQL station coordinates use six-decimal precision.
    latitude: search.latitude.toFixed(6),
    longitude: search.longitude.toFixed(6),
    radius_km: String(search.radiusKm),
  });
}

function toManagedMarker(station: ManagedStation): StationMarker {
  const availablePoints = station.charge_points.filter(
    (point) => point.is_bookable && point.status === "available",
  );
  const connectors = availablePoints
    .map((point) => `${point.connector_type} · ${point.max_power_kw} kW`)
    .join(", ");

  return {
    id: station.id,
    name: station.name,
    latitude: station.latitude,
    longitude: station.longitude,
    address: `${station.address_line_1}, ${station.city}, ${station.state}`,
    source: "chargemate",
    bookable: availablePoints.length > 0,
    status: station.status,
    distanceKm: station.distance_km ?? null,
    connectorSummary: connectors || "No bookable connector currently available",
    externalDetailsUrl: null,
  };
}

function toExternalMarker(station: ExternalStation): StationMarker {
  const address = [
    station.address.line_1,
    station.address.town,
    station.address.state,
  ]
    .filter(Boolean)
    .join(", ");
  const connectors = station.connections
    .map((connection) =>
      connection.power_kw
        ? `${connection.type} · ${connection.power_kw} kW`
        : connection.type,
    )
    .join(", ");

  return {
    id: `ocm-${station.external_id}`,
    name: station.name,
    latitude: station.latitude,
    longitude: station.longitude,
    address: address || "Address not provided",
    source: "open_charge_map",
    bookable: false,
    status: station.status ?? "Status unknown",
    distanceKm: station.distance_km,
    connectorSummary: connectors || "Connector details unavailable",
    externalDetailsUrl: station.details_url,
  };
}
