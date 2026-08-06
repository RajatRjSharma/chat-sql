"use client";

import { FormEvent, useEffect, useState } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { OtpForm } from "@/components/auth/otp-form";
import { RegisterForm } from "@/components/auth/register-form";
import { api, ApiError } from "@/lib/api";
import type { AuthSession } from "@/lib/auth";
import { validatePasswordClient } from "@/lib/password";

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
  const [registrationEnabled, setRegistrationEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .authConfig()
      .then((cfg) => {
        if (!cancelled) setRegistrationEnabled(cfg.registration_enabled);
      })
      .catch(() => {
        // Fail closed — match server default when config cannot be loaded.
        if (!cancelled) setRegistrationEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!registrationEnabled && mode === "register") {
      setMode("login");
    }
  }, [registrationEnabled, mode]);

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
    if (!registrationEnabled) {
      setError("New account registration is currently disabled.");
      setMode("login");
      return;
    }
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
      if (result.status === "verified") {
        setIdentifier(result.email);
        setMode("login");
        setInfo(result.message);
        return;
      }
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
    <div className="relative min-h-[100dvh] overflow-x-hidden bg-[var(--bg-shell)] text-[var(--text-on-dark)]">
      <div aria-hidden className="pointer-events-none absolute inset-0 mesh-grid opacity-40" />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-20 top-16 h-80 w-80 rounded-full bg-[var(--accent)]/12 blur-3xl animate-fade-in"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-[28rem] w-[28rem] rounded-full bg-[var(--accent-light)]/15 blur-3xl"
      />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-lg flex-col justify-center px-5 py-12 pb-[max(3rem,var(--safe-bottom))] pt-[max(3rem,var(--safe-top))]">
        <header className="mb-10 animate-fade-in">
          <p className="break-words font-[family-name:var(--font-display)] text-2xl leading-tight tracking-tight md:text-3xl">
            Voice-Driven Data Analyst
          </p>
          <p className="mt-2 break-words text-sm text-[var(--text-muted-dark)]">
            Sign in to analyze your warehouses
          </p>
        </header>

        <div className="animate-rise rounded-2xl border border-[var(--border-shell)] bg-[var(--bg-shell-elevated)]/80 p-5 backdrop-blur-sm sm:p-6 md:p-8">
          {mode === "login" ? (
            <LoginForm
              identifier={identifier}
              password={password}
              busy={busy}
              registrationEnabled={registrationEnabled}
              onIdentifierChange={setIdentifier}
              onPasswordChange={setPassword}
              onSubmit={handleLogin}
              onSwitchToRegister={() => {
                setMode("register");
                setError(null);
                setInfo(null);
                clearSecrets();
              }}
            />
          ) : null}

          {mode === "register" && registrationEnabled ? (
            <RegisterForm
              email={email}
              username={username}
              password={password}
              passwordConfirm={passwordConfirm}
              busy={busy}
              onEmailChange={setEmail}
              onUsernameChange={setUsername}
              onPasswordChange={setPassword}
              onPasswordConfirmChange={setPasswordConfirm}
              onSubmit={handleRegister}
              onSwitchToLogin={() => {
                setMode("login");
                setError(null);
                setInfo(null);
                clearSecrets();
              }}
            />
          ) : null}

          {mode === "otp" ? (
            <OtpForm
              otpEmail={otpEmail}
              code={code}
              busy={busy}
              onOtpEmailChange={setOtpEmail}
              onCodeChange={setCode}
              onSubmit={handleVerifyOtp}
              onResend={handleResend}
              onBackToLogin={() => {
                setMode("login");
                setError(null);
                setInfo(null);
              }}
            />
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
