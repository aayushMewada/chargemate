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
  const response = await requestJson<ManagedStationDetailResponse>(
    `/stations/${stationId}`,
    {
      method: "PATCH",
      authenticated: true,
      body: JSON.stringify({version, status}),
    },
  );
  return response.station;
}

export async function updateOwnedChargePoint(
  stationId: string,
  chargePointId: string,
  version: number,
  changes: {status?: ChargePointStatus; is_bookable?: boolean},
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
    latitude: String(search.latitude),
    longitude: String(search.longitude),
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
