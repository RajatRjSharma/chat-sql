/** Client-side auth session — access + refresh JWTs (stateless). */

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  role: string;
  email_verified: boolean;
  created_at?: string | null;
};

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  user: AuthUser;
};

const STORAGE_KEY = "meridian.auth.v2";

export function loadAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  try {
    // Migrate away from v1 (access-only) sessions.
    localStorage.removeItem("meridian.auth.v1");
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed?.accessToken || !parsed?.refreshToken || !parsed?.user?.id) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveAuthSession(session: AuthSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearAuthSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("meridian.auth.v1");
  } catch {
    /* ignore */
  }
}

export function authHeaders(): Record<string, string> {
  const session = loadAuthSession();
  if (!session?.accessToken) return {};
  return { Authorization: `Bearer ${session.accessToken}` };
}

export function sessionFromTokenResponse(token: {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: AuthUser;
}): AuthSession {
  return {
    accessToken: token.access_token,
    refreshToken: token.refresh_token,
    expiresAt: Date.now() + token.expires_in * 1000,
    user: token.user,
  };
}
