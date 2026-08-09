import {type FormEvent, useCallback, useEffect, useState} from "react";
import {
  createOwnedStation,
  listOwnedStations,
  type ChargePointStatus,
  type StationStatus,
  updateOwnedChargePoint,
  updateOwnedStationStatus,
} from "../api/stations";
import {ApiError} from "../api/client";
import type {
  ChargePoint,
  ConnectorType,
  ManagedStation,
  StationCreateInput,
} from "../types/station";

const STATION_STATUSES: StationStatus[] = [
  "draft",
  "active",
  "inactive",
  "maintenance",
];
const CHARGE_POINT_STATUSES: ChargePointStatus[] = [
  "available",
  "out_of_service",
  "maintenance",
  "retired",
];
const CONNECTOR_TYPES: ConnectorType[] = [
  "ccs_2",
  "type_2",
  "chademo",
  "gb_t",
  "bharat_dc_001",
];

type ConnectorDraft = {
  code: string;
  connector_type: ConnectorType;
  power_type: "ac" | "dc";
  max_power_kw: string;
  booking_fee: string;
  is_bookable: boolean;
};

type StationDraft = {
  name: string;
  description: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  postal_code: string;
  country_code: string;
  latitude: string;
  longitude: string;
  timezone: string;
  phone: string;
  is_24_hours: boolean;
  charge_points: ConnectorDraft[];
};

export function StationAdminPanel({open, onClose}: {open: boolean; onClose: () => void}) {
  const [stations, setStations] = useState<ManagedStation[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<StationDraft>(newStationDraft);

  const loadStations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listOwnedStations(page);
      setStations(result.stations);
      setPages(Math.max(result.pagination.pages, 1));
      setTotal(result.pagination.total);
    } catch (caught) {
      setError(apiMessage(caught, "Your stations could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    if (open) void loadStations();
  }, [loadStations, open]);

  if (!open) return null;

  async function createStation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      const input: StationCreateInput = {
        name: draft.name,
        description: optional(draft.description),
        address_line_1: draft.address_line_1,
        address_line_2: optional(draft.address_line_2),
        city: draft.city,
        state: draft.state,
        postal_code: draft.postal_code,
        country_code: draft.country_code,
        latitude: requiredNumber(draft.latitude, "latitude"),
        longitude: requiredNumber(draft.longitude, "longitude"),
        timezone: draft.timezone,
        phone: optional(draft.phone),
        is_24_hours: draft.is_24_hours,
        charge_points: draft.charge_points.map((point) => ({
          code: point.code,
          connector_type: point.connector_type,
          power_type: point.power_type,
          max_power_kw: requiredNumber(point.max_power_kw, "maximum power"),
          booking_fee: requiredNumber(point.booking_fee, "booking fee"),
          is_bookable: point.is_bookable,
        })),
      };
      const created = await createOwnedStation(input);
      const result = await listOwnedStations(1);
      setStations(result.stations);
      setPage(1);
      setPages(Math.max(result.pagination.pages, 1));
      setTotal(result.pagination.total);
      setDraft(newStationDraft());
      setCreateOpen(false);
      setNotice(`${created.name} was created as a draft station.`);
    } catch (caught) {
      setError(apiMessage(caught, "The station could not be created."));
    } finally {
      setCreating(false);
    }
  }

  function updateConnector(index: number, changes: Partial<ConnectorDraft>) {
    setDraft((current) => ({
      ...current,
      charge_points: current.charge_points.map((point, pointIndex) =>
        pointIndex === index ? {...point, ...changes} : point,
      ),
    }));
  }

  async function changeStationStatus(station: ManagedStation, status: StationStatus) {
    const key = `station-${station.id}`;
    setSavingKey(key);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateOwnedStationStatus(station.id, station.version, status);
      setStations((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${updated.name} is now ${readable(updated.status)}.`);
    } catch (caught) {
      await handleMutationError(caught);
    } finally {
      setSavingKey(null);
    }
  }

  async function changeChargePoint(
    station: ManagedStation,
    chargePoint: ChargePoint,
    changes: {status?: ChargePointStatus; is_bookable?: boolean},
  ) {
    const key = `point-${chargePoint.id}`;
    setSavingKey(key);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateOwnedChargePoint(
        station.id,
        chargePoint.id,
        chargePoint.version,
        changes,
      );
      setStations((current) => current.map((item) => item.id !== station.id ? item : {
        ...item,
        charge_points: item.charge_points.map((point) => point.id === updated.id ? updated : point),
      }));
      setNotice(`${updated.code} was updated successfully.`);
    } catch (caught) {
      await handleMutationError(caught);
    } finally {
      setSavingKey(null);
    }
  }

  async function handleMutationError(caught: unknown) {
    if (caught instanceof ApiError && caught.code === "station_state_conflict") {
      setError("This resource changed or an operational rule blocked the update. Fresh data has been loaded.");
      await loadStations();
      return;
    }
    setError(apiMessage(caught, "The station update could not be completed."));
  }

  return (
    <div className="admin-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !savingKey) onClose();
    }}>
      <section className="admin-panel" role="dialog" aria-modal="true" aria-labelledby="admin-title">
        <div className="admin-header">
          <div>
            <p className="eyebrow">Operator controls</p>
            <h2 id="admin-title">Station dashboard</h2>
            <span>{total} managed station{total === 1 ? "" : "s"}</span>
          </div>
          <div className="admin-header-actions">
            <button
              className="add-station-button"
              type="button"
              onClick={() => setCreateOpen((value) => !value)}
              disabled={creating}
            >
              {createOpen ? "Cancel setup" : "Add station"}
            </button>
            <button className="admin-close-button" type="button" onClick={onClose} disabled={Boolean(savingKey) || creating} aria-label="Close station dashboard">×</button>
          </div>
        </div>

        {notice && <div className="dashboard-notice" role="status">{notice}</div>}
        {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}

        {createOpen && (
          <form className="station-create-form" onSubmit={(event) => void createStation(event)}>
            <div className="station-form-heading">
              <div><p className="eyebrow">New location</p><h3>Create a station</h3></div>
              <span>It starts in draft status</span>
            </div>

            <div className="station-form-grid">
              <label>Station name<input required minLength={2} maxLength={120} value={draft.name} onChange={(event) => setDraft({...draft, name: event.target.value})} /></label>
              <label>Phone (optional)<input maxLength={20} value={draft.phone} onChange={(event) => setDraft({...draft, phone: event.target.value})} /></label>
              <label className="station-form-wide">Description (optional)<textarea maxLength={2000} value={draft.description} onChange={(event) => setDraft({...draft, description: event.target.value})} /></label>
              <label className="station-form-wide">Address line 1<input required minLength={3} maxLength={255} value={draft.address_line_1} onChange={(event) => setDraft({...draft, address_line_1: event.target.value})} /></label>
              <label className="station-form-wide">Address line 2 (optional)<input maxLength={255} value={draft.address_line_2} onChange={(event) => setDraft({...draft, address_line_2: event.target.value})} /></label>
              <label>City<input required minLength={2} value={draft.city} onChange={(event) => setDraft({...draft, city: event.target.value})} /></label>
              <label>State<input required minLength={2} value={draft.state} onChange={(event) => setDraft({...draft, state: event.target.value})} /></label>
              <label>Postal code<input required minLength={3} value={draft.postal_code} onChange={(event) => setDraft({...draft, postal_code: event.target.value})} /></label>
              <label>Country code<input required minLength={2} maxLength={2} value={draft.country_code} onChange={(event) => setDraft({...draft, country_code: event.target.value.toUpperCase()})} /></label>
              <label>Latitude<input required type="number" min="-90" max="90" step="0.000001" value={draft.latitude} onChange={(event) => setDraft({...draft, latitude: event.target.value})} /></label>
              <label>Longitude<input required type="number" min="-180" max="180" step="0.000001" value={draft.longitude} onChange={(event) => setDraft({...draft, longitude: event.target.value})} /></label>
              <label>Timezone<input required value={draft.timezone} onChange={(event) => setDraft({...draft, timezone: event.target.value})} /></label>
              <label className="station-check"><input type="checkbox" checked={draft.is_24_hours} onChange={(event) => setDraft({...draft, is_24_hours: event.target.checked})} /> Open 24 hours</label>
            </div>

            <div className="connector-form-heading">
              <div><h4>Initial connectors</h4><span>At least one connector is required.</span></div>
              <button type="button" onClick={() => setDraft((current) => ({...current, charge_points: [...current.charge_points, newConnectorDraft()]}))}>Add connector</button>
            </div>

            <div className="connector-form-list">
              {draft.charge_points.map((point, index) => (
                <fieldset key={index}>
                  <legend>Connector {index + 1}</legend>
                  <label>Code<input required maxLength={50} value={point.code} onChange={(event) => updateConnector(index, {code: event.target.value.toUpperCase()})} /></label>
                  <label>Connector type<select value={point.connector_type} onChange={(event) => updateConnector(index, {connector_type: event.target.value as ConnectorType})}>{CONNECTOR_TYPES.map((type) => <option key={type} value={type}>{readable(type)}</option>)}</select></label>
                  <label>Power type<select value={point.power_type} onChange={(event) => updateConnector(index, {power_type: event.target.value as "ac" | "dc"})}><option value="dc">DC</option><option value="ac">AC</option></select></label>
                  <label>Maximum kW<input required type="number" min="0.01" step="0.01" value={point.max_power_kw} onChange={(event) => updateConnector(index, {max_power_kw: event.target.value})} /></label>
                  <label>Booking fee (₹)<input required type="number" min="0" step="0.01" value={point.booking_fee} onChange={(event) => updateConnector(index, {booking_fee: event.target.value})} /></label>
                  <label className="station-check"><input type="checkbox" checked={point.is_bookable} onChange={(event) => updateConnector(index, {is_bookable: event.target.checked})} /> Bookable</label>
                  {draft.charge_points.length > 1 && <button className="remove-connector" type="button" onClick={() => setDraft((current) => ({...current, charge_points: current.charge_points.filter((_, pointIndex) => pointIndex !== index)}))}>Remove</button>}
                </fieldset>
              ))}
            </div>

            <button className="create-station-submit" type="submit" disabled={creating}>{creating ? "Creating station..." : "Create station and connectors"}</button>
          </form>
        )}

        <div className="admin-station-list">
          {loading ? (
            <div className="dashboard-empty">Loading managed stations...</div>
          ) : stations.length === 0 ? (
            <div className="dashboard-empty">
              <strong>No stations assigned</strong>
              <span>Use Add station to create your first charging location.</span>
            </div>
          ) : stations.map((station) => (
            <article className="admin-station-card" key={station.id}>
              <div className="admin-station-heading">
                <div>
                  <span className={`operator-status operator-status--${station.status}`}>{readable(station.status)}</span>
                  <h3>{station.name}</h3>
                  <p>{station.address_line_1}, {station.city}, {station.state}</p>
                </div>
                <label>
                  Station status
                  <select
                    value={station.status}
                    disabled={savingKey === `station-${station.id}`}
                    onChange={(event) => void changeStationStatus(station, event.target.value as StationStatus)}
                  >
                    {STATION_STATUSES.map((status) => <option key={status} value={status}>{readable(status)}</option>)}
                  </select>
                </label>
              </div>

              <div className="admin-station-meta">
                <span>{station.is_24_hours ? "Open 24 hours" : station.timezone}</span>
                <span>Station version {station.version}</span>
                <span>{station.charge_points.length} connector{station.charge_points.length === 1 ? "" : "s"}</span>
              </div>

              <div className="admin-point-list">
                {station.charge_points.map((point) => (
                  <div className="admin-point-row" key={point.id}>
                    <div>
                      <strong>{point.code}</strong>
                      <span>{readable(point.connector_type)} · {point.max_power_kw} kW · ₹{point.booking_fee.toFixed(2)}</span>
                    </div>
                    <label>
                      Status
                      <select
                        value={point.status}
                        disabled={savingKey === `point-${point.id}`}
                        onChange={(event) => void changeChargePoint(station, point, {
                          status: event.target.value as ChargePointStatus,
                        })}
                      >
                        {CHARGE_POINT_STATUSES.map((status) => <option key={status} value={status}>{readable(status)}</option>)}
                      </select>
                    </label>
                    <label className="bookable-toggle">
                      <input
                        type="checkbox"
                        checked={point.is_bookable}
                        disabled={savingKey === `point-${point.id}`}
                        onChange={(event) => void changeChargePoint(station, point, {is_bookable: event.target.checked})}
                      />
                      Bookable
                    </label>
                    <span className="point-version">v{point.version}</span>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>

        {pages > 1 && (
          <div className="dashboard-pagination">
            <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>Previous</button>
            <span>Page {page} of {pages}</span>
            <button type="button" disabled={page >= pages || loading} onClick={() => setPage((value) => value + 1)}>Next</button>
          </div>
        )}
      </section>
    </div>
  );
}

function readable(value: string): string {
  return value.replaceAll("_", " ");
}

function apiMessage(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) return caught.message;
  return caught instanceof Error ? caught.message : fallback;
}

function optional(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function requiredNumber(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`Enter a valid ${label}.`);
  return parsed;
}

function newConnectorDraft(): ConnectorDraft {
  return {
    code: "",
    connector_type: "ccs_2",
    power_type: "dc",
    max_power_kw: "60",
    booking_fee: "50",
    is_bookable: true,
  };
}

function newStationDraft(): StationDraft {
  return {
    name: "",
    description: "",
    address_line_1: "",
    address_line_2: "",
    city: "Indore",
    state: "Madhya Pradesh",
    postal_code: "",
    country_code: "IN",
    latitude: "22.719600",
    longitude: "75.857700",
    timezone: "Asia/Kolkata",
    phone: "",
    is_24_hours: false,
    charge_points: [newConnectorDraft()],
  };
}
