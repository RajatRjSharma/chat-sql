"use client";

import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PASSWORD_MIN_LENGTH } from "@/lib/password";

type RegisterFormProps = {
  email: string;
  username: string;
  password: string;
  passwordConfirm: string;
  busy: boolean;
  onEmailChange: (value: string) => void;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onPasswordConfirmChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onSwitchToLogin: () => void;
};

export function RegisterForm({
  email,
  username,
  password,
  passwordConfirm,
  busy,
  onEmailChange,
  onUsernameChange,
  onPasswordChange,
  onPasswordConfirmChange,
  onSubmit,
  onSwitchToLogin,
}: RegisterFormProps) {
  return (
    <form className="space-y-4" onSubmit={onSubmit} autoComplete="on">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-tight">
          Create account
        </h1>
        <p className="mt-1 text-sm text-[var(--text-muted-dark)]">
          Strong password required
        </p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => onEmailChange(e.target.value)}
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
          onChange={(e) => onUsernameChange(e.target.value)}
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
          onChange={(e) => onPasswordChange(e.target.value)}
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
          onChange={(e) => onPasswordConfirmChange(e.target.value)}
          required
          minLength={PASSWORD_MIN_LENGTH}
          className="border-[var(--border-shell)] bg-[var(--bg-shell)] text-[var(--text-on-dark)]"
        />
      </div>
      <Button type="submit" className="w-full" disabled={busy} size="lg">
        {busy ? "Creating account…" : "Create account"}
      </Button>
      <p className="text-center text-sm text-[var(--text-muted-dark)]">
        Already have an account?{" "}
        <button
          type="button"
          className="text-[var(--accent)] underline-offset-2 hover:underline"
          onClick={onSwitchToLogin}
        >
          Sign in
        </button>
      </p>
    </form>
  );
}
