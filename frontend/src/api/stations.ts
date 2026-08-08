import {getJson} from "./client";
import type {
  Coordinates,
  ExternalStation,
  ExternalStationResponse,
  ManagedStation,
  ManagedStationResponse,
  StationMarker,
} from "../types/station";

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
  };
}
