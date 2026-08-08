import {useEffect, useState} from "react";
import {cancelBooking, listMyBookings} from "../api/bookings";
import {ApiError} from "../api/client";
import type {Booking, BookingStatus, CancellationResult} from "../types/booking";

type BookingFilter = "all" | BookingStatus;

const FILTERS: Array<{value: BookingFilter; label: string}> = [
  {value: "all", label: "All"},
  {value: "held", label: "Held"},
  {value: "payment_pending", label: "Payment pending"},
  {value: "confirmed", label: "Confirmed"},
  {value: "cancelled", label: "Cancelled"},
  {value: "expired", label: "Expired"},
];

const CANCELLABLE = new Set<BookingStatus>([
  "held",
  "payment_pending",
  "confirmed",
]);

export function BookingsPanel({open, onClose}: {open: boolean; onClose: () => void}) {
  const [filter, setFilter] = useState<BookingFilter>("all");
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError(null);
    setNotice(null);

    listMyBookings(filter === "all" ? undefined : filter, page)
      .then((result) => {
        if (!active) return;
        setBookings(result.bookings);
        setPages(Math.max(result.pagination.pages, 1));
        setTotal(result.pagination.total);
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "Bookings could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [filter, open, page]);

  if (!open) return null;

  async function cancel(selected: Booking) {
    setCancellingId(selected.id);
    setError(null);
    setNotice(null);
    try {
      const result = await cancelBooking(selected.id, selected.version);
      setBookings((current) =>
        filter !== "all" && result.booking.status !== filter
          ? current.filter((booking) => booking.id !== result.booking.id)
          : current.map((booking) =>
              booking.id === result.booking.id ? result.booking : booking,
            ),
      );
      if (filter !== "all" && result.booking.status !== filter) {
        setTotal((value) => Math.max(0, value - 1));
      }
      setConfirmingId(null);
      setNotice(cancellationNotice(result));
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "booking_state_conflict") {
        setError("This booking changed before cancellation. Close and reopen the dashboard for its latest version.");
      } else {
        setError(caught instanceof ApiError ? caught.message : "The booking could not be cancelled.");
      }
    } finally {
      setCancellingId(null);
    }
  }

  return (
    <div className="bookings-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !cancellingId) onClose();
    }}>
      <section className="bookings-panel" role="dialog" aria-modal="true" aria-labelledby="bookings-title">
        <div className="bookings-header">
          <div>
            <p className="eyebrow">Your charging plans</p>
            <h2 id="bookings-title">My bookings</h2>
            <span>{total} booking{total === 1 ? "" : "s"}</span>
          </div>
          <button type="button" onClick={onClose} aria-label="Close bookings">×</button>
        </div>

        <div className="booking-filters" aria-label="Booking status filters">
          {FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={filter === option.value ? "booking-filter--active" : ""}
              onClick={() => {
                setFilter(option.value);
                setPage(1);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>

        {notice && <div className="dashboard-notice" role="status">{notice}</div>}
        {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}

        <div className="bookings-list">
          {loading ? (
            <div className="dashboard-empty">Loading your bookings...</div>
          ) : bookings.length === 0 ? (
            <div className="dashboard-empty">
              <strong>No bookings in this view</strong>
              <span>Reserve a verified ChargeMate connector to see it here.</span>
            </div>
          ) : (
            bookings.map((booking) => (
              <BookingCard
                key={booking.id}
                booking={booking}
                now={now}
                confirming={confirmingId === booking.id}
                cancelling={cancellingId === booking.id}
                onAskCancel={() => setConfirmingId(booking.id)}
                onKeep={() => setConfirmingId(null)}
                onCancel={() => void cancel(booking)}
              />
            ))
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

function BookingCard({
  booking,
  now,
  confirming,
  cancelling,
  onAskCancel,
  onKeep,
  onCancel,
}: {
  booking: Booking;
  now: number;
  confirming: boolean;
  cancelling: boolean;
  onAskCancel: () => void;
  onKeep: () => void;
  onCancel: () => void;
}) {
  const holdRemaining = booking.status === "held"
    ? remainingTime(booking.hold_expires_at, now)
    : null;
  const latestPayment = booking.payments[0];
  const latestRefund = latestPayment?.refund;

  return (
    <article className="booking-card">
      <div className="booking-card__heading">
        <div>
          <span className={`booking-status booking-status--${booking.status}`}>
            {booking.status.replaceAll("_", " ")}
          </span>
          <h3>{booking.charge_point.station.name}</h3>
          <p>{booking.charge_point.station.city}, {booking.charge_point.station.state}</p>
        </div>
        <strong>{booking.total_amount === null ? "—" : `₹${booking.total_amount.toFixed(2)}`}</strong>
      </div>

      <div className="booking-facts">
        <div><span>Connector</span><strong>{booking.charge_point.code} · {booking.charge_point.max_power_kw} kW</strong></div>
        <div><span>Starts</span><strong>{formatDateTime(booking.starts_at)}</strong></div>
        <div><span>Ends</span><strong>{formatDateTime(booking.ends_at)}</strong></div>
        <div><span>Version</span><strong>{booking.version}</strong></div>
      </div>

      {holdRemaining && <div className="hold-countdown">Hold expires in {holdRemaining}</div>}
      {latestPayment && (
        <div className="payment-summary">
          <span>Payment: <strong>{latestPayment.status}</strong></span>
          {latestRefund && (
            <span>Refund: <strong>{latestRefund.status}</strong> · ₹{latestRefund.amount.toFixed(2)}</span>
          )}
        </div>
      )}

      {CANCELLABLE.has(booking.status) && (
        <div className="booking-actions">
          {confirming ? (
            <>
              <span>Cancel this booking?</span>
              <button type="button" className="keep-booking" onClick={onKeep}>Keep it</button>
              <button type="button" className="confirm-cancel" onClick={onCancel} disabled={cancelling}>
                {cancelling ? "Cancelling..." : "Confirm cancellation"}
              </button>
            </>
          ) : (
            <button type="button" className="cancel-booking" onClick={onAskCancel}>Cancel booking</button>
          )}
        </div>
      )}
    </article>
  );
}

function remainingTime(expiresAt: string | null, now: number): string | null {
  if (!expiresAt) return null;
  const seconds = Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function cancellationNotice(result: CancellationResult): string {
  if (!result.refund) return "Booking cancelled. No captured payment required a refund.";
  if (result.error) return `${result.error.message} Refund status: ${result.refund.status}.`;
  return `Booking cancelled. Refund status: ${result.refund.status}.`;
}
