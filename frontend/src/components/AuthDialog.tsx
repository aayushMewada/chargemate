import {type FormEvent, useEffect, useState} from "react";
import {ApiError} from "../api/client";
import {useAuth} from "../auth/AuthContext";

export type AuthMode = "login" | "register";

type AuthDialogProps = {
  open: boolean;
  initialMode: AuthMode;
  onClose: () => void;
};

export function AuthDialog({open, initialMode, onClose}: AuthDialogProps) {
  const {login, register} = useAuth();
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setMode(initialMode);
    setError(null);
    setDetails([]);
  }, [initialMode, open]);

  if (!open) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setDetails([]);

    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");

    try {
      if (mode === "login") {
        await login({
          identifier: String(form.get("identifier") ?? ""),
          password,
        });
      } else {
        const phone = String(form.get("phone") ?? "").trim();
        await register({
          email: String(form.get("email") ?? ""),
          username: String(form.get("username") ?? ""),
          full_name: String(form.get("full_name") ?? ""),
          phone: phone || null,
          password,
        });
      }
      onClose();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setDetails(
          caught.details
            .map((detail) => detail.message)
            .filter((message): message is string => Boolean(message)),
        );
      } else {
        setError("The authentication service could not be reached.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose();
      }}
    >
      <section
        className="auth-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
      >
        <button
          className="dialog-close"
          type="button"
          onClick={onClose}
          disabled={submitting}
          aria-label="Close authentication dialog"
        >
          ×
        </button>
        <p className="eyebrow">Your ChargeMate account</p>
        <h2 id="auth-dialog-title">
          {mode === "login" ? "Welcome back" : "Start charging with certainty"}
        </h2>
        <p className="dialog-intro">
          {mode === "login"
            ? "Log in to manage bookings and charging history."
            : "Create an account to reserve verified ChargeMate connectors."}
        </p>

        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "auth-tab--active" : ""}
            onClick={() => setMode("login")}
          >
            Log in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "auth-tab--active" : ""}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          {mode === "register" ? (
            <>
              <label>
                Full name
                <input name="full_name" autoComplete="name" minLength={2} required />
              </label>
              <label>
                Email address
                <input name="email" type="email" autoComplete="email" required />
              </label>
              <label>
                Username
                <input
                  name="username"
                  autoComplete="username"
                  minLength={3}
                  maxLength={50}
                  pattern="[a-z0-9_]+"
                  title="Use lowercase letters, numbers, and underscores."
                  required
                />
              </label>
              <label>
                Phone <span>(optional, international format)</span>
                <input name="phone" type="tel" autoComplete="tel" placeholder="+919876543210" />
              </label>
            </>
          ) : (
            <label>
              Email or username
              <input name="identifier" autoComplete="username" minLength={3} required autoFocus />
            </label>
          )}

          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 12 : 1}
              maxLength={128}
              required
            />
          </label>

          {error && (
            <div className="form-error" role="alert">
              <strong>{error}</strong>
              {details.length > 0 && (
                <ul>{details.map((detail) => <li key={detail}>{detail}</li>)}</ul>
              )}
            </div>
          )}

          <button className="auth-submit" type="submit" disabled={submitting}>
            {submitting
              ? "Please wait..."
              : mode === "login"
                ? "Log in securely"
                : "Create my account"}
          </button>
        </form>

        <p className="auth-security-note">
          Your refresh token is protected in an HTTP-only cookie and cannot be
          read by frontend JavaScript.
        </p>
      </section>
    </div>
  );
}
