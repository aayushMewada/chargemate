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
  starts_at: string;
  ends_at: string;
  hold_expires_at: string;
  status: BookingStatus;
  total_amount: number | null;
  currency: string;
  version: number;
  created_at: string;
};

export type CreateBookingInput = {
  charge_point_id: string;
  starts_at: string;
  ends_at: string;
};
