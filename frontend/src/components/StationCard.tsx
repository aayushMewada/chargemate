import type {StationMarker} from "../types/station";

type StationCardProps = {
  station: StationMarker;
  selected: boolean;
  onSelect: () => void;
};

export function StationCard({station, selected, onSelect}: StationCardProps) {
  return (
    <button
      type="button"
      className={`station-card${selected ? " station-card--selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="station-card__topline">
        <span className={`source-badge source-badge--${station.source}`}>
          {station.source === "chargemate" ? "ChargeMate" : "Open data"}
        </span>
        {station.distanceKm !== null && (
          <span className="distance">{station.distanceKm.toFixed(1)} km</span>
        )}
      </span>
      <strong>{station.name}</strong>
      <span className="station-card__address">{station.address}</span>
      <span className="station-card__connector">{station.connectorSummary}</span>
      <span className="station-card__footer">
        <span className={station.bookable ? "availability" : "location-only"}>
          {station.bookable ? "Available to book" : "Location only"}
        </span>
        <span aria-hidden="true">→</span>
      </span>
    </button>
  );
}
