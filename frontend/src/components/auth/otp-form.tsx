"use client";

import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type OtpFormProps = {
  otpEmail: string;
  code: string;
  busy: boolean;
  onOtpEmailChange: (value: string) => void;
  onCodeChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onResend: () => void;
  onBackToLogin: () => void;
};

export function OtpForm({
  otpEmail,
  code,
  busy,
  onOtpEmailChange,
  onCodeChange,
  onSubmit,
  onResend,
  onBackToLogin,
}: OtpFormProps) {
  return (
    <form className="space-y-4" onSubmit={onSubmit}>
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
          onChange={(e) => onOtpEmailChange(e.target.value)}
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
          onChange={(e) => onCodeChange(e.target.value)}
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
          onClick={() => void onResend()}
        >
          Resend code
        </button>
        <button
          type="button"
          className="text-[var(--accent)] underline-offset-2 hover:underline"
          onClick={onBackToLogin}
        >
          Back to sign in
        </button>
      </div>
    </form>
  );
}
