import {requestJson} from "./client";
import type {Booking, CreateBookingInput} from "../types/booking";

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
