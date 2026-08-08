import {ApiError, requestJson} from "./client";
import type {
  Booking,
  BookingPage,
  BookingStatus,
  CancellationResult,
  CreateBookingInput,
} from "../types/booking";

export async function createBookingHold(
  input: CreateBookingInput,
): Promise<Booking> {
  const response = await requestJson<{booking: Booking}>("/bookings", {
    method: "POST",
    authenticated: true,
    body: JSON.stringify(input),
  });
  return response.booking;
}

export function listMyBookings(
  status?: BookingStatus,
  page = 1,
): Promise<BookingPage> {
  const query = new URLSearchParams({page: String(page), per_page: "20"});
  if (status) query.set("status", status);
  return requestJson<BookingPage>(`/bookings/me?${query.toString()}`, {
    authenticated: true,
  });
}

export async function cancelBooking(
  bookingId: string,
  version: number,
): Promise<CancellationResult> {
  try {
    return await requestJson<CancellationResult>(
      `/bookings/${bookingId}/cancel`,
      {
        method: "POST",
        authenticated: true,
        body: JSON.stringify({version}),
      },
    );
  } catch (caught) {
    if (
      caught instanceof ApiError &&
      caught.status === 502 &&
      isCancellationResult(caught.payload)
    ) {
      return caught.payload;
    }
    throw caught;
  }
}

function isCancellationResult(value: unknown): value is CancellationResult {
  return Boolean(
    value &&
      typeof value === "object" &&
      "booking" in value,
  );
}
