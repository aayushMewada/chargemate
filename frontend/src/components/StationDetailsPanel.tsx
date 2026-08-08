import {type FormEvent, useEffect, useMemo, useState} from "react";
import {createBookingHold} from "../api/bookings";
import {ApiError} from "../api/client";
import {getManagedStation} from "../api/stations";
import {useAuth} from "../auth/AuthContext";
import type {Booking} from "../types/booking";
import type {ChargePoint, ManagedStation, StationMarker} from "../types/station";

type StationDetailsPanelProps = {
  station: StationMarker | null;
  onClose: () => void;
  onRequireLogin: () => void;
};

export function StationDetailsPanel({
  station,
  onClose,
  onRequireLogin,
}: StationDetailsPanelProps) {
  const {user} = useAuth();
  const [details, setDetails] = useState<ManagedStation | null>(null);
  const [selectedPointId, setSelectedPointId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);

  const bookablePoints = useMemo(
    () =>
      details?.charge_points.filter(
        (point) => point.is_bookable && point.status === "available",
      ) ?? [],
    [details],
  );

  useEffect(() => {
    if (!station) return;

    const {start, end} = defaultBookingWindow();
    setStartsAt(start);
    setEndsAt(end);
    setDetails(null);
    setSelectedPointId("");
    setBooking(null);
    setError(null);

    if (station.source !== "chargemate") return;

    const controller = new AbortController();
    setLoading(true);
    getManagedStation(station.id, controller.signal)
      .then((managedStation) => {
        setDetails(managedStation);
        const firstBookable = managedStation.charge_points.find(
          (point) => point.is_bookable && point.status === "available",
        );
        setSelectedPointId(firstBookable?.id ?? "");
      })
      .catch((caught) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError("The latest station details could not be loaded.");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [station]);

  if (!station) return null;

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) {
      onRequireLogin();
      return;
    }
    if (!selectedPointId) {
      setError("Select an available charge point.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setBooking(null);

    try {
      const created = await createBookingHold({
        charge_point_id: selectedPointId,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
      });
      setBooking(created);
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.code === "booking_unavailable") {
          setError("That connector was just reserved for this time. Choose another time slot.");
        } else {
          setError(caught.message);
        }
      } else {
        setError("The booking service could not be reached.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="details-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !submitting) onClose();
    }}>
      <aside className="station-details" role="dialog" aria-modal="true" aria-labelledby="station-title">
        <button className="details-close" type="button" onClick={onClose} aria-label="Close station details">×</button>
        <div className="details-hero">
          <span className={`source-badge source-badge--${station.source}`}>
            {station.source === "chargemate" ? "Verified ChargeMate station" : "Open Charge Map location"}
          </span>
          <h2 id="station-title">{station.name}</h2>
          <p>{station.address}</p>
          <div className="details-meta">
            <span>{station.status.replaceAll("_", " ")}</span>
            {station.distanceKm !== null && <span>{station.distanceKm.toFixed(1)} km away</span>}
          </div>
        </div>

        {station.source === "open_charge_map" ? (
          <section className="external-details">
            <h3>Public location information</h3>
            <p>{station.connectorSummary}</p>
            <div className="information-callout">
              This station comes from community-maintained open data. Its live
              availability is not verified, so it cannot be reserved on ChargeMate.
            </div>
            {station.externalDetailsUrl && (
              <a href={station.externalDetailsUrl} target="_blank" rel="noreferrer">
                View source details ↗
              </a>
            )}
          </section>
        ) : (
          <>
            <section className="connector-section">
              <h3>Choose a connector</h3>
              {loading ? (
                <p className="details-muted">Loading current connector status...</p>
              ) : details ? (
                <div className="connector-grid">
                  {details.charge_points.map((point) => (
                    <ConnectorOption
                      key={point.id}
                      point={point}
                      selected={selectedPointId === point.id}
                      onSelect={() => setSelectedPointId(point.id)}
                    />
                  ))}
                </div>
              ) : null}
            </section>

            <form className="booking-form" onSubmit={(event) => void submitBooking(event)}>
              <h3>Reserve a time</h3>
              <div className="booking-time-grid">
                <label>
                  Starts
                  <input
                    type="datetime-local"
                    value={startsAt}
                    min={localDateTimeValue(new Date())}
                    onChange={(event) => {
                      const nextStart = event.target.value;
                      setStartsAt(nextStart);
                      if (new Date(endsAt) <= new Date(nextStart)) {
                        setEndsAt(localDateTimeValue(new Date(new Date(nextStart).getTime() + 60 * 60 * 1000)));
                      }
                    }}
                    required
                  />
                </label>
                <label>
                  Ends
                  <input
                    type="datetime-local"
                    value={endsAt}
                    min={startsAt}
                    onChange={(event) => setEndsAt(event.target.value)}
                    required
                  />
                </label>
              </div>

              {!user && (
                <p className="login-callout">Log in before reserving this connector.</p>
              )}
              {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}
              {booking && <BookingHoldSuccess booking={booking} />}

              <button
                className="reserve-button"
                type="submit"
                disabled={submitting || loading || bookablePoints.length === 0 || Boolean(booking)}
              >
                {booking
                  ? "Slot held"
                  : submitting
                    ? "Securing your slot..."
                    : user
                      ? "Hold this charging slot"
                      : "Log in to reserve"}
              </button>
            </form>
          </>
        )}
      </aside>
    </div>
  );
}

function ConnectorOption({
  point,
  selected,
  onSelect,
}: {
  point: ChargePoint;
  selected: boolean;
  onSelect: () => void;
}) {
  const available = point.is_bookable && point.status === "available";
  return (
    <button
      type="button"
      className={`connector-option${selected ? " connector-option--selected" : ""}`}
      onClick={onSelect}
      disabled={!available}
      aria-pressed={selected}
    >
      <span><strong>{point.code}</strong><em>{point.status.replaceAll("_", " ")}</em></span>
      <span>{point.connector_type.replaceAll("_", " ")} · {point.power_type.toUpperCase()}</span>
      <span><b>{point.max_power_kw} kW</b><b>₹{point.booking_fee.toFixed(2)}</b></span>
    </button>
  );
}

function BookingHoldSuccess({booking}: {booking: Booking}) {
  return (
    <div className="booking-success" role="status">
      <strong>Your charging slot is temporarily held.</strong>
      <span>Hold expires {new Date(booking.hold_expires_at).toLocaleString()}.</span>
      <span>Booking version {booking.version} · Payment is the next step.</span>
    </div>
  );
}

function defaultBookingWindow(): {start: string; end: string} {
  const start = new Date(Date.now() + 60 * 60 * 1000);
  start.setMinutes(Math.ceil(start.getMinutes() / 30) * 30, 0, 0);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  return {start: localDateTimeValue(start), end: localDateTimeValue(end)};
}

function localDateTimeValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}
