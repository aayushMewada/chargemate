import {type FormEvent, useState} from "react";
import {ApiError} from "../api/client";
import {useAuth} from "../auth/AuthContext";

export function AccountSecurityPanel({
  open,
  onClose,
  onSignedOut,
}: {
  open: boolean;
  onClose: () => void;
  onSignedOut: (message: string) => void;
}) {
  const {changePassword, logoutAllDevices} = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setError("The new-password confirmation does not match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      onSignedOut("Password changed. Every device was signed out; log in with your new password.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The password could not be changed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function signOutEverywhere() {
    setSubmitting(true);
    setError(null);
    try {
      await logoutAllDevices();
      onSignedOut("Every ChargeMate session was revoked. Log in again to continue.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Sessions could not be revoked.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="security-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !submitting) onClose();
    }}>
      <section className="security-panel" role="dialog" aria-modal="true" aria-labelledby="security-title">
        <div className="security-header">
          <div><p className="eyebrow">Account protection</p><h2 id="security-title">Security settings</h2></div>
          <button type="button" onClick={onClose} disabled={submitting} aria-label="Close security settings">×</button>
        </div>

        {error && <div className="form-error" role="alert"><strong>{error}</strong></div>}

        <form className="password-form" onSubmit={(event) => void submitPassword(event)}>
          <div><h3>Change password</h3><p>This revokes access and refresh tokens on every device.</p></div>
          <label>Current password<input required type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
          <label>New password<input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label>
          <label>Confirm new password<input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
          <button type="submit" disabled={submitting}>{submitting ? "Updating..." : "Change password and sign out"}</button>
        </form>

        <div className="session-danger-zone">
          <div><h3>Log out all devices</h3><p>Immediately revoke this browser and every other active ChargeMate session.</p></div>
          <button type="button" disabled={submitting} onClick={() => void signOutEverywhere()}>{submitting ? "Revoking..." : "Log out everywhere"}</button>
        </div>
      </section>
    </div>
  );
}
