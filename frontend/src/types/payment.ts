export type PaymentStatus =
  | "initiated"
  | "order_created"
  | "authorized"
  | "captured"
  | "failed"
  | "refunded";

export type CheckoutOrder = {
  payment: {
    id: string;
    status: PaymentStatus;
    amount: number;
    amount_subunits: number;
    currency: string;
    provider: "razorpay";
    provider_order_id: string;
  };
  booking: {
    id: string;
    status: "payment_pending";
    version: number;
  };
  checkout: {
    key_id: string;
    order_id: string;
    amount: number;
    currency: string;
  };
};

export type RazorpayCheckoutResult = {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
};

export type VerifiedPayment = {
  id: string;
  status: PaymentStatus;
  provider_order_id: string;
  provider_payment_id: string;
};
