import {useCallback, useEffect, useState} from "react";
import {
  listOwnedStations,
  type ChargePointStatus,
  type StationStatus,
  updateOwnedChargePoint,
  updateOwnedStationStatus,
} from "../api/stations";
import {ApiError} from "../api/client";
import type {ChargePoint, ManagedStation} from "../types/station";

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

export function StationAdminPanel({open, onClose}: {open: boolean; onClose: () => void}) {
  const [stations, setStations] = useState<ManagedStation[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
          <button type="button" onClick={onClose} disabled={Boolean(savingKey)} aria-label="Close station dashboard">×</button>
        </div>

        {notice && <div className="dashboard-notice" role="status">{notice}</div>}
        {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}

        <div className="admin-station-list">
          {loading ? (
            <div className="dashboard-empty">Loading managed stations...</div>
          ) : stations.length === 0 ? (
            <div className="dashboard-empty">
              <strong>No stations assigned</strong>
              <span>Create a station through the operator API to manage it here.</span>
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
  return caught instanceof ApiError ? caught.message : fallback;
}
