import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearAuthSession,
  loadAuthSession,
  onAuthCleared,
  saveAuthSession,
  sessionFromTokenResponse,
  type AuthUser,
} from "@/lib/auth";

const user: AuthUser = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "analyst@example.com",
  username: "analyst",
  role: "analyst",
  email_verified: true,
};

describe("auth session storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("stores profile only (no JWT fields)", () => {
    saveAuthSession({
      expiresAt: Date.now() + 60_000,
      user,
    });

    const raw = localStorage.getItem("vdda.auth.v2");
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.user.username).toBe("analyst");
    expect(parsed.accessToken).toBeUndefined();
    expect(parsed.refreshToken).toBeUndefined();
  });

  it("loads a valid session and clears legacy token keys", () => {
    localStorage.setItem(
      "vdda.auth.v1",
      JSON.stringify({
        accessToken: "legacy",
        refreshToken: "legacy",
        expiresAt: Date.now() + 60_000,
        user,
      }),
    );
    saveAuthSession(sessionFromTokenResponse({ expires_in: 1800, user }));

    const session = loadAuthSession();
    expect(session?.user.email).toBe("analyst@example.com");
    expect(session?.expiresAt).toBeGreaterThan(Date.now());
    expect(localStorage.getItem("vdda.auth.v1")).toBeNull();
  });

  it("clearAuthSession removes current and legacy keys", () => {
    saveAuthSession({ expiresAt: Date.now() + 60_000, user });
    localStorage.setItem("vdda.auth.v1", "x");
    clearAuthSession();
    expect(localStorage.getItem("vdda.auth.v2")).toBeNull();
    expect(localStorage.getItem("vdda.auth.v1")).toBeNull();
    expect(loadAuthSession()).toBeNull();
  });

  it("notifies subscribers when the session is cleared (e.g. 401)", () => {
    const onCleared = vi.fn();
    const unsubscribe = onAuthCleared(onCleared);
    saveAuthSession({ expiresAt: Date.now() + 60_000, user });
    clearAuthSession();
    expect(onCleared).toHaveBeenCalledTimes(1);
    unsubscribe();
    clearAuthSession();
    expect(onCleared).toHaveBeenCalledTimes(1);
  });
});
