import {useEffect, useMemo, useState} from "react";
import {listMyChargingSessions} from "../api/chargingSessions";
import {ApiError} from "../api/client";
import type {
  ChargingSession,
  ChargingSessionStatus,
} from "../types/chargingSession";

type SessionFilter = "all" | ChargingSessionStatus;

const FILTERS: Array<{value: SessionFilter; label: string}> = [
  {value: "all", label: "All sessions"},
  {value: "active", label: "Active"},
  {value: "completed", label: "Completed"},
  {value: "interrupted", label: "Interrupted"},
];

export function ChargingHistoryPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [filter, setFilter] = useState<SessionFilter>("all");
  const [sessions, setSessions] = useState<ChargingSession[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError(null);

    listMyChargingSessions(filter === "all" ? undefined : filter, page)
      .then((result) => {
        if (!active) return;
        setSessions(result.charging_sessions);
        setTotal(result.pagination.total);
        setPages(Math.max(result.pagination.pages, 1));
      })
      .catch((caught) => {
        if (!active) return;
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Charging history could not be loaded.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [filter, open, page]);

  const visibleEnergy = useMemo(
    () => sessions.reduce(
      (sum, session) => sum + (session.energy_consumed_kwh ?? 0),
      0,
    ),
    [sessions],
  );

  if (!open) return null;

  return (
    <div className="history-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="history-panel" role="dialog" aria-modal="true" aria-labelledby="history-title">
        <header className="history-header">
          <div>
            <p className="eyebrow">Metered energy records</p>
            <h2 id="history-title">Charging history</h2>
            <span>{total} session{total === 1 ? "" : "s"}</span>
          </div>
          <button type="button" onClick={onClose} aria-label="Close charging history">×</button>
        </header>

        <div className="history-summary">
          <div><span>Visible energy</span><strong>{visibleEnergy.toFixed(3)} kWh</strong></div>
          <div><span>Active now</span><strong>{sessions.filter((session) => session.status === "active").length}</strong></div>
          <div><span>Completed</span><strong>{sessions.filter((session) => session.status === "completed").length}</strong></div>
        </div>

        <div className="history-filters" aria-label="Charging session filters">
          {FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={filter === option.value ? "history-filter--active" : ""}
              onClick={() => {
                setFilter(option.value);
                setPage(1);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>

        {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}

        <div className="session-list">
          {loading ? (
            <div className="dashboard-empty">Loading charging history...</div>
          ) : sessions.length === 0 ? (
            <div className="dashboard-empty">
              <strong>No charging sessions yet</strong>
              <span>Completed charger usage will appear here with meter readings.</span>
            </div>
          ) : (
            sessions.map((session) => <SessionCard key={session.id} session={session} />)
          )}
        </div>

        {pages > 1 && (
          <div className="dashboard-pagination">
            <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
            <span>Page {page} of {pages}</span>
            <button type="button" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Next</button>
          </div>
        )}
      </section>
    </div>
  );
}

function SessionCard({session}: {session: ChargingSession}) {
  const duration = session.ended_at
    ? formatDuration(new Date(session.ended_at).getTime() - new Date(session.started_at).getTime())
    : "In progress";

  return (
    <article className="session-card">
      <div className="session-card__heading">
        <div>
          <span className={`session-status session-status--${session.status}`}>
            {session.status === "active" && <i aria-hidden="true" />}
            {session.status}
          </span>
          <h3>{session.charge_point.station.name}</h3>
          <p>{session.charge_point.station.city}, {session.charge_point.station.state}</p>
        </div>
        <div className="energy-reading">
          <strong>{session.energy_consumed_kwh?.toFixed(3) ?? "—"}</strong>
          <span>kWh consumed</span>
        </div>
      </div>

      <div className="session-meter">
        <div><span>Started</span><strong>{formatDateTime(session.started_at)}</strong></div>
        <div><span>Ended</span><strong>{session.ended_at ? formatDateTime(session.ended_at) : "Charging now"}</strong></div>
        <div><span>Duration</span><strong>{duration}</strong></div>
        <div><span>Connector</span><strong>{session.charge_point.code} · {session.charge_point.max_power_kw} kW</strong></div>
        <div><span>Start meter</span><strong>{session.meter_start_kwh.toFixed(3)} kWh</strong></div>
        <div><span>End meter</span><strong>{session.meter_end_kwh?.toFixed(3) ?? "—"} kWh</strong></div>
      </div>
    </article>
  );
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString([], {dateStyle: "medium", timeStyle: "short"});
}

function formatDuration(milliseconds: number): string {
  const totalMinutes = Math.max(0, Math.round(milliseconds / 60_000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}
