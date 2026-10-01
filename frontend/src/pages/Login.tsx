import { useState } from "react";
import { useAuth } from "../lib/AuthContext";
import { ApiError } from "../lib/api";

export default function Login() {
  const { ownerExists, bootstrap, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!ownerExists && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      if (ownerExists) await login(username, password);
      else await bootstrap(username, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl text-lg font-bold text-white shadow-md" style={{ background: "linear-gradient(135deg, var(--color-brand-500), var(--color-brand-700))" }}>
            LP
          </span>
        </div>
        <div className="card">
          <h1 className="text-center text-xl font-semibold tracking-tight text-slate-900">PostPilot AI</h1>
          <p className="mt-1 text-center text-sm text-slate-500">{ownerExists ? "Sign in to your dashboard." : "Create the owner account for this local app. This runs once, on this machine."}</p>
          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <div>
              <label htmlFor="username" className="field-label">
                Username
              </label>
              <input id="username" required minLength={3} value={username} onChange={(e) => setUsername(e.target.value)} className="field-input mt-1" />
            </div>
            <div>
              <label htmlFor="password" className="field-label">
                Password
              </label>
              <input id="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="field-input mt-1" />
            </div>
            {!ownerExists && (
              <div>
                <label htmlFor="confirm" className="field-label">
                  Confirm password
                </label>
                <input id="confirm" type="password" required minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} className="field-input mt-1" />
              </div>
            )}
            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
            <button type="submit" disabled={busy} className="btn-primary w-full">
              {busy ? "Please wait…" : ownerExists ? "Sign in" : "Create owner account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
