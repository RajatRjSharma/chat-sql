"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import type { AuthSession } from "@/lib/auth";
import { PASSWORD_MIN_LENGTH, validatePasswordClient } from "@/lib/password";

type Mode = "login" | "register" | "otp";

type AuthGateProps = {
  onAuthenticated: (session: AuthSession) => void;
};

export function AuthGate({ onAuthenticated }: AuthGateProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [otpEmail, setOtpEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  function clearSecrets() {
    setPassword("");
    setPasswordConfirm("");
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const session = await api.login({
        identifier: identifier.trim(),
        password,
      });
      clearSecrets();
      onAuthenticated(session);
    } catch (err) {
      const detail =
        err instanceof ApiError ? err.detail : "Could not sign in";
      setError(detail);
      if (err instanceof ApiError && err.status === 403) {
        setOtpEmail(identifier.includes("@") ? identifier.trim().toLowerCase() : "");
        setMode("otp");
        setInfo("Verify your email with the code we sent, then try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleRegister(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);

    if (password !== passwordConfirm) {
      setError("Passwords do not match");
      setBusy(false);
      return;
    }
    const strengthError = validatePasswordClient(password, { username, email });
    if (strengthError) {
      setError(strengthError);
      setBusy(false);
      return;
    }

    try {
      const result = await api.register({
        email: email.trim().toLowerCase(),
        username: username.trim(),
        password,
        password_confirm: passwordConfirm,
      });
      clearSecrets();
      setOtpEmail(result.email);
      setMode("otp");
      setInfo(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not register");
    } finally {
      setBusy(false);
    }
  }

  async function handleVerifyOtp(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await api.verifyOtp({
        email: otpEmail.trim().toLowerCase(),
        code: code.trim(),
      });
      setCode("");
      onAuthenticated(session);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Invalid verification code");
    } finally {
      setBusy(false);
    }
  }

  async function handleResend() {
    if (!otpEmail.trim()) {
      setError("Enter the email you registered with");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.resendOtp(otpEmail.trim().toLowerCase());
      setInfo(result.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not resend code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <div aria-hidden className="pointer-events-none absolute inset-0 mesh-grid opacity-40" />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-20 top-16 h-80 w-80 rounded-full bg-[var(--accent)]/12 blur-3xl animate-fade-in"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-[28rem] w-[28rem] rounded-full bg-[#1d4ed8]/12 blur-3xl"
      />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-lg flex-col justify-center px-5 py-12">
        <header className="mb-10 animate-fade-in">
          <p className="font-[family-name:var(--font-display)] text-3xl tracking-tight md:text-4xl">
            Meridian
          </p>
          <p className="mt-2 text-sm text-[var(--text-muted-dark)]">
            Sign in to analyze your warehouses
          </p>
        </header>

        <div className="animate-rise rounded-2xl border border-[var(--border-shell)] bg-[var(--bg-shell-elevated)]/80 p-6 backdrop-blur-sm md:p-8">
          {mode === "login" ? (
            <form className="space-y-4" onSubmit={handleLogin} autoComplete="on">
              <div>
                <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-tight">
                  Sign in
                </h1>
                <p className="mt-1 text-sm text-[var(--text-muted-dark)]">
                  Email or username + password
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="identifier">Email or username</Label>
                <Input
                  id="identifier"
                  autoComplete="username"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="login-password">Password</Label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy} size="lg">
                {busy ? "Signing in…" : "Sign in"}
              </Button>
              <p className="text-center text-sm text-[var(--text-muted-dark)]">
                New here?{" "}
                <button
                  type="button"
                  className="text-[var(--accent)] underline-offset-2 hover:underline"
                  onClick={() => {
                    setMode("register");
                    setError(null);
                    setInfo(null);
                    clearSecrets();
                  }}
                >
                  Create an account
                </button>
              </p>
            </form>
          ) : null}

          {mode === "register" ? (
            <form className="space-y-4" onSubmit={handleRegister} autoComplete="on">
              <div>
                <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-tight">
                  Create account
                </h1>
                <p className="mt-1 text-sm text-[var(--text-muted-dark)]">
                  Strong password + email OTP verification
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  minLength={3}
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-password">Password</Label>
                <Input
                  id="reg-password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={PASSWORD_MIN_LENGTH}
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
                <p className="text-[11px] leading-relaxed text-[var(--text-muted-dark)]">
                  At least {PASSWORD_MIN_LENGTH} chars, with upper, lower, number, and
                  special character.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-password-confirm">Confirm password</Label>
                <Input
                  id="reg-password-confirm"
                  type="password"
                  autoComplete="new-password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  required
                  minLength={PASSWORD_MIN_LENGTH}
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy} size="lg">
                {busy ? "Sending code…" : "Register & send OTP"}
              </Button>
              <p className="text-center text-sm text-[var(--text-muted-dark)]">
                Already have an account?{" "}
                <button
                  type="button"
                  className="text-[var(--accent)] underline-offset-2 hover:underline"
                  onClick={() => {
                    setMode("login");
                    setError(null);
                    setInfo(null);
                    clearSecrets();
                  }}
                >
                  Sign in
                </button>
              </p>
            </form>
          ) : null}

          {mode === "otp" ? (
            <form className="space-y-4" onSubmit={handleVerifyOtp}>
              <div>
                <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-tight">
                  Verify email
                </h1>
                <p className="mt-1 text-sm text-[var(--text-muted-dark)]">
                  Enter the 6-digit code sent via Gmail SMTP
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="otp-email">Email</Label>
                <Input
                  id="otp-email"
                  type="email"
                  value={otpEmail}
                  onChange={(e) => setOtpEmail(e.target.value)}
                  required
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="otp-code">Verification code</Label>
                <Input
                  id="otp-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                  minLength={4}
                  maxLength={8}
                  className="border-[var(--border-shell)] bg-[var(--bg-shell)] font-mono tracking-[0.3em] text-[var(--text-on-dark)]"
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy} size="lg">
                {busy ? "Verifying…" : "Verify & continue"}
              </Button>
              <div className="flex items-center justify-between gap-3 text-sm">
                <button
                  type="button"
                  className="text-[var(--text-muted-dark)] underline-offset-2 hover:underline"
                  disabled={busy}
                  onClick={() => void handleResend()}
                >
                  Resend code
                </button>
                <button
                  type="button"
                  className="text-[var(--accent)] underline-offset-2 hover:underline"
                  onClick={() => {
                    setMode("login");
                    setError(null);
                    setInfo(null);
                  }}
                >
                  Back to sign in
                </button>
              </div>
            </form>
          ) : null}

          {info ? (
            <p className="mt-4 text-sm text-[var(--accent)]" role="status">
              {info}
            </p>
          ) : null}
          {error ? (
            <p
              className="mt-4 rounded-md border border-[var(--error)]/30 bg-[var(--error)]/10 px-3 py-2 text-sm text-[#fecaca]"
              role="alert"
            >
              {error}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
