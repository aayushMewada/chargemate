import {useRef, useState} from "react";
import {createCheckoutOrder, verifyCheckoutPayment} from "../api/payments";
import {ApiError} from "../api/client";
import {useAuth} from "../auth/AuthContext";
import {
  createRazorpayCheckout,
  loadRazorpayCheckout,
} from "../payments/razorpay";
import type {Booking} from "../types/booking";
import type {RazorpayCheckoutResult, VerifiedPayment} from "../types/payment";

type CheckoutState = "idle" | "creating" | "open" | "verifying" | "verified";

export function PaymentCheckout({booking}: {booking: Booking}) {
  const {user} = useAuth();
  const idempotencyKey = useRef(crypto.randomUUID());
  const [state, setState] = useState<CheckoutState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [verifiedPayment, setVerifiedPayment] = useState<VerifiedPayment | null>(null);

  async function beginCheckout() {
    if (!user) return;
    setState("creating");
    setError(null);

    try {
      const [order] = await Promise.all([
        createCheckoutOrder(booking.id, booking.version, idempotencyKey.current),
        loadRazorpayCheckout(),
      ]);

      const checkout = createRazorpayCheckout({
        key: order.checkout.key_id,
        amount: order.checkout.amount,
        currency: order.checkout.currency,
        name: "ChargeMate",
        description: `Charging slot ${new Date(booking.starts_at).toLocaleString()}`,
        order_id: order.checkout.order_id,
        prefill: {
          name: user.full_name,
          email: user.email,
          contact: user.phone ?? undefined,
        },
        theme: {color: "#8dbd2d"},
        modal: {
          ondismiss: () => {
            setState("idle");
            setError("Checkout was closed. Your payment order can be reopened safely.");
          },
        },
        handler: (result) => void handleSuccess(result),
      });

      checkout.on("payment.failed", (failure) => {
        setState("idle");
        setError(
          failure.error?.description ??
            failure.error?.reason ??
            "Razorpay could not complete the test payment.",
        );
      });
      setState("open");
      checkout.open();
    } catch (caught) {
      setState("idle");
      setError(paymentErrorMessage(caught));
    }
  }

  async function handleSuccess(result: RazorpayCheckoutResult) {
    setState("verifying");
    setError(null);
    try {
      const payment = await verifyCheckoutPayment(result);
      setVerifiedPayment(payment);
      setState("verified");
    } catch (caught) {
      setState("idle");
      setError(paymentErrorMessage(caught));
    }
  }

  if (verifiedPayment) {
    return (
      <div className="payment-verified" role="status">
        <strong>Payment response verified securely.</strong>
        <span>Payment {verifiedPayment.provider_payment_id}</span>
        <span>
          Status: {verifiedPayment.status}. Final booking confirmation comes
          from the signed capture webhook.
        </span>
      </div>
    );
  }

  return (
    <div className="checkout-section">
      <div>
        <strong>Booking fee</strong>
        <span>₹{booking.total_amount?.toFixed(2)} {booking.currency}</span>
      </div>
      <p>
        Razorpay Checkout runs in test mode. No real money is charged when test
        credentials are configured.
      </p>
      {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}
      <button
        className="payment-button"
        type="button"
        disabled={state === "creating" || state === "verifying"}
        onClick={() => void beginCheckout()}
      >
        {state === "creating"
          ? "Creating secure order..."
          : state === "verifying"
            ? "Verifying payment..."
            : "Continue to Razorpay"}
      </button>
    </div>
  );
}

function paymentErrorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.code === "payment_state_conflict") {
      return "This hold expired or its booking version changed. Create a new hold.";
    }
    return caught.message;
  }
  if (caught instanceof Error) return caught.message;
  return "The payment flow could not be started.";
}
