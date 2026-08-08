export type BookingStatus =
  | "held"
  | "payment_pending"
  | "confirmed"
  | "active"
  | "completed"
  | "cancelled"
  | "expired";

export type Booking = {
  id: string;
  user_id: string;
  charge_point_id: string;
  charge_point: {
    id: string;
    code: string;
    connector_type: string;
    power_type: string;
    max_power_kw: number;
    station: {
      id: string;
      name: string;
      city: string;
      state: string;
    };
  };
  starts_at: string;
  ends_at: string;
  hold_expires_at: string;
  status: BookingStatus;
  total_amount: number | null;
  currency: string;
  version: number;
  payments: Array<{
    id: string;
    status: "initiated" | "order_created" | "authorized" | "captured" | "failed" | "refunded";
    amount: number;
    currency: string;
    provider_payment_id: string | null;
    created_at: string;
    refund: Refund | null;
  }>;
  created_at: string;
};

export type BookingPage = {
  bookings: Booking[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    pages: number;
  };
};

export type RefundStatus = "requested" | "pending" | "processed" | "failed";

export type Refund = {
  id: string;
  payment_id: string;
  status: RefundStatus;
  amount: number;
  currency: string;
  provider_refund_id: string | null;
  processed_at: string | null;
};

export type CancellationResult = {
  booking: Booking;
  refund?: Refund;
  error?: {
    code: string;
    message: string;
  };
};

export type CreateBookingInput = {
  charge_point_id: string;
  starts_at: string;
  ends_at: string;
};
