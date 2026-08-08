import {requestJson} from "./client";
import type {CheckoutOrder, RazorpayCheckoutResult, VerifiedPayment} from "../types/payment";

export async function createCheckoutOrder(
  bookingId: string,
  bookingVersion: number,
  idempotencyKey: string,
): Promise<CheckoutOrder> {
  return requestJson<CheckoutOrder>("/payments/orders", {
    method: "POST",
    authenticated: true,
    body: JSON.stringify({
      booking_id: bookingId,
      booking_version: bookingVersion,
      idempotency_key: idempotencyKey,
    }),
  });
}

export async function verifyCheckoutPayment(
  result: RazorpayCheckoutResult,
): Promise<VerifiedPayment> {
  const response = await requestJson<{payment: VerifiedPayment}>(
    "/payments/verify",
    {
      method: "POST",
      authenticated: true,
      body: JSON.stringify(result),
    },
  );
  return response.payment;
}
