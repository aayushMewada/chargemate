import {useCallback, useEffect, useState} from "react";
import {
  completeChargingSession,
  listChargingOperations,
  startChargingSession,
} from "../api/chargingSessions";
import {ApiError} from "../api/client";
import type {ChargingOperation} from "../types/chargingSession";

export function ChargingOperationsPanel({open, onClose}: {open: boolean; onClose: () => void}) {
  const [operations, setOperations] = useState<ChargingOperation[]>([]);
  const [readings, setReadings] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadOperations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listChargingOperations(page);
      setOperations(result.operations);
      setPages(Math.max(result.pagination.pages, 1));
      setTotal(result.pagination.total);
    } catch (caught) {
      setError(messageFor(caught, "Charging operations could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    if (open) void loadOperations();
  }, [loadOperations, open]);

  if (!open) return null;

  async function submit(operation: ChargingOperation) {
    const session = operation.charging_session;
    const actionId = session?.id ?? operation.booking.id;
    const readingValue = readings[actionId];
    const reading = Number(readingValue);
    if (!readingValue?.trim() || !Number.isFinite(reading) || reading < 0) {
      setError("Enter a valid non-negative cumulative meter reading.");
      return;
    }

    setSubmittingId(actionId);
    setError(null);
    setNotice(null);
    try {
      if (session) {
        if (reading < session.meter_start_kwh) {
          setError("The ending meter reading cannot be below the starting reading.");
          return;
        }
        const response = await completeChargingSession(session.id, session.version, reading);
        setNotice(
          `Session completed: ${response.charging_session.energy_consumed_kwh?.toFixed(3)} kWh consumed.`,
        );
      } else {
        await startChargingSession(operation.booking.id, operation.booking.version, reading);
        setNotice(`Charging started for ${operation.customer.full_name}.`);
      }
      setReadings((current) => ({...current, [actionId]: ""}));
      await loadOperations();
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "charging_session_state_conflict") {
        await loadOperations();
        setError("This booking or session changed. The operations queue has been refreshed.");
      } else if (caught instanceof ApiError && caught.code === "outside_charging_window") {
        setError("This booking is outside its permitted start window.");
      } else {
        setError(messageFor(caught, "The charging operation could not be completed."));
      }
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <div className="operations-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !submittingId) onClose();
    }}>
      <section className="operations-panel" role="dialog" aria-modal="true" aria-labelledby="operations-title">
        <div className="operations-header">
          <div>
            <p className="eyebrow">Live station workflow</p>
            <h2 id="operations-title">Charging operations</h2>
            <span>{total} actionable booking{total === 1 ? "" : "s"}</span>
          </div>
          <button type="button" onClick={onClose} disabled={Boolean(submittingId)} aria-label="Close operations">×</button>
        </div>

        {notice && <div className="dashboard-notice" role="status">{notice}</div>}
        {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}

        <div className="operations-list">
          {loading ? (
            <div className="dashboard-empty">Loading charging operations...</div>
          ) : operations.length === 0 ? (
            <div className="dashboard-empty">
              <strong>No charging operations right now</strong>
              <span>Confirmed bookings will appear here when they are ready for check-in.</span>
            </div>
          ) : operations.map((operation) => {
            const session = operation.charging_session;
            const actionId = session?.id ?? operation.booking.id;
            return (
              <article className="operation-card" key={operation.booking.id}>
                <div className="operation-heading">
                  <div>
                    <span className={`session-status session-status--${session ? "active" : "completed"}`}>
                      {session ? "Charging now" : "Confirmed booking"}
                    </span>
                    <h3>{operation.customer.full_name}</h3>
                    <p>{operation.customer.email}</p>
                  </div>
                  <strong>{operation.charge_point.code}</strong>
                </div>

                <div className="operation-facts">
                  <div><span>Station</span><strong>{operation.station.name}</strong></div>
                  <div><span>Connector</span><strong>{readable(operation.charge_point.connector_type)} · {operation.charge_point.max_power_kw} kW</strong></div>
                  <div><span>Starts</span><strong>{formatDateTime(operation.booking.starts_at)}</strong></div>
                  <div><span>Ends</span><strong>{formatDateTime(operation.booking.ends_at)}</strong></div>
                </div>

                {session && (
                  <p className="operation-meter-start">
                    Started {formatDateTime(session.started_at)} at <strong>{session.meter_start_kwh.toFixed(3)} kWh</strong>
                  </p>
                )}

                <div className="meter-action">
                  <label>
                    {session ? "Ending cumulative meter (kWh)" : "Starting cumulative meter (kWh)"}
                    <input
                      type="number"
                      min={session?.meter_start_kwh ?? 0}
                      step="0.001"
                      value={readings[actionId] ?? ""}
                      placeholder={session ? String(session.meter_start_kwh) : "0.000"}
                      onChange={(event) => setReadings((current) => ({
                        ...current,
                        [actionId]: event.target.value,
                      }))}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={submittingId === actionId}
                    onClick={() => void submit(operation)}
                  >
                    {submittingId === actionId
                      ? "Saving..."
                      : session ? "Complete session" : "Start charging"}
                  </button>
                </div>
                <span className="operation-version">
                  {session ? `Session version ${session.version}` : `Booking version ${operation.booking.version}`}
                </span>
              </article>
            );
          })}
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

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString([], {dateStyle: "medium", timeStyle: "short"});
}

function messageFor(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.message : fallback;
}
