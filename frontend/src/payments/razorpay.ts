import type {RazorpayCheckoutResult} from "../types/payment";

const CHECKOUT_SCRIPT_URL = "https://checkout.razorpay.com/v1/checkout.js";
let checkoutScriptPromise: Promise<void> | null = null;

export type RazorpayOptions = {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (result: RazorpayCheckoutResult) => void;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  theme?: {color: string};
  modal?: {ondismiss?: () => void};
};

export type RazorpayFailure = {
  error?: {
    description?: string;
    reason?: string;
  };
};

type RazorpayInstance = {
  open: () => void;
  on: (event: "payment.failed", handler: (failure: RazorpayFailure) => void) => void;
};

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

export function loadRazorpayCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  if (checkoutScriptPromise) return checkoutScriptPromise;

  const loadPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${CHECKOUT_SCRIPT_URL}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(), {once: true});
      existing.addEventListener(
        "error",
        () => reject(new Error("Razorpay Checkout could not be loaded.")),
        {once: true},
      );
      return;
    }

    const script = document.createElement("script");
    script.src = CHECKOUT_SCRIPT_URL;
    script.async = true;
    script.addEventListener("load", () => resolve(), {once: true});
    script.addEventListener(
      "error",
      () => reject(new Error("Razorpay Checkout could not be loaded.")),
      {once: true},
    );
    document.head.append(script);
  }).catch((error) => {
    checkoutScriptPromise = null;
    throw error;
  });

  checkoutScriptPromise = loadPromise;
  return loadPromise;
}

export function createRazorpayCheckout(options: RazorpayOptions): RazorpayInstance {
  const Razorpay = window.Razorpay;
  if (!Razorpay) {
    throw new Error("Razorpay Checkout is not available.");
  }
  return new Razorpay(options);
}
