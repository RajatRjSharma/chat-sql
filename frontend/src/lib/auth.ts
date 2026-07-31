/** Client-side auth profile cache — JWTs live in httpOnly cookies only. */

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  role: string;
  email_verified: boolean;
  created_at?: string | null;
};

/** Lightweight client mirror of the server session (no tokens). */
export type AuthSession = {
  expiresAt: number;
  user: AuthUser;
};

const STORAGE_KEY = "vdda.auth.v2";
const LEGACY_KEYS = [
  "vdda.auth.v1",
  "meridian.auth.v1",
  "meridian.auth.v2",
] as const;

function clearLegacyKeys(): void {
  for (const key of LEGACY_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  }
}

export function loadAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  try {
    clearLegacyKeys();
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed?.user?.id || typeof parsed.expiresAt !== "number") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveAuthSession(session: AuthSession): void {
  clearLegacyKeys();
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      expiresAt: session.expiresAt,
      user: session.user,
    } satisfies AuthSession),
  );
}

export function clearAuthSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
    clearLegacyKeys();
  } catch {
    /* ignore */
  }
}

export function sessionFromTokenResponse(token: {
  expires_in: number;
  user: AuthUser;
}): AuthSession {
  return {
    expiresAt: Date.now() + token.expires_in * 1000,
    user: token.user,
  };
}
