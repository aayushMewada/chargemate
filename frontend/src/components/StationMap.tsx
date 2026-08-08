import {useEffect} from "react";
import {CircleMarker, MapContainer, Popup, TileLayer, useMap} from "react-leaflet";
import {latLngBounds} from "leaflet";
import type {Coordinates, StationMarker} from "../types/station";

type StationMapProps = {
  center: Coordinates;
  stations: StationMarker[];
  selectedStationId: string | null;
  onSelectStation: (stationId: string) => void;
};

export function StationMap({
  center,
  stations,
  selectedStationId,
  onSelectStation,
}: StationMapProps) {
  return (
    <MapContainer
      center={[center.latitude, center.longitude]}
      zoom={13}
      className="station-map"
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapViewport center={center} stations={stations} />
      <CircleMarker
        center={[center.latitude, center.longitude]}
        radius={8}
        pathOptions={{color: "#ffffff", fillColor: "#3178ff", fillOpacity: 1, weight: 3}}
      >
        <Popup>Your search center</Popup>
      </CircleMarker>
      {stations.map((station) => {
        const isSelected = station.id === selectedStationId;
        const markerColor = station.bookable ? "#c7f36b" : "#ffb86b";
        return (
          <CircleMarker
            key={station.id}
            center={[station.latitude, station.longitude]}
            radius={isSelected ? 12 : 9}
            pathOptions={{
              color: isSelected ? "#ffffff" : "#102721",
              fillColor: markerColor,
              fillOpacity: 1,
              weight: isSelected ? 4 : 2,
            }}
            eventHandlers={{click: () => onSelectStation(station.id)}}
          >
            <Popup>
              <div className="map-popup">
                <strong>{station.name}</strong>
                <span>{station.address}</span>
                <span>{station.connectorSummary}</span>
                <em>{station.bookable ? "Bookable on ChargeMate" : "Location only"}</em>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}

function MapViewport({
  center,
  stations,
}: {
  center: Coordinates;
  stations: StationMarker[];
}) {
  const map = useMap();

  useEffect(() => {
    if (stations.length === 0) {
      map.setView([center.latitude, center.longitude], 13);
      return;
    }

    const bounds = latLngBounds([
      [center.latitude, center.longitude],
      ...stations.map(
        (station) => [station.latitude, station.longitude] as [number, number],
      ),
    ]);
    map.fitBounds(bounds, {padding: [48, 48], maxZoom: 14});
  }, [center, map, stations]);

  return null;
}
