"use client";

import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type LoginFormProps = {
  identifier: string;
  password: string;
  busy: boolean;
  registrationEnabled?: boolean;
  onIdentifierChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onSwitchToRegister: () => void;
};

export function LoginForm({
  identifier,
  password,
  busy,
  registrationEnabled = false,
  onIdentifierChange,
  onPasswordChange,
  onSubmit,
  onSwitchToRegister,
}: LoginFormProps) {
  return (
    <form className="space-y-4" onSubmit={onSubmit} autoComplete="on">
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
          onChange={(e) => onIdentifierChange(e.target.value)}
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
          onChange={(e) => onPasswordChange(e.target.value)}
          required
          className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
        />
      </div>
      <Button type="submit" className="w-full" disabled={busy} size="lg">
        {busy ? "Signing in…" : "Sign in"}
      </Button>
      {registrationEnabled ? (
        <p className="text-center text-sm text-[var(--text-muted-dark)]">
          New here?{" "}
          <button
            type="button"
            className="text-[var(--accent)] underline-offset-2 hover:underline"
            onClick={onSwitchToRegister}
          >
            Create an account
          </button>
        </p>
      ) : (
        <p className="text-center text-sm text-[var(--text-muted-dark)]">
          New accounts are currently closed. Contact an admin if you need access.
        </p>
      )}
    </form>
  );
}
