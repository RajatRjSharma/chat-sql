/** Shared password rules — mirrored on the API. */

export const PASSWORD_MIN_LENGTH = 12;

export function validatePasswordClient(
  password: string,
  opts?: { username?: string; email?: string },
): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Password must be at least ${PASSWORD_MIN_LENGTH} characters`;
  }
  if (password.length > 72) {
    return "Password must be at most 72 characters";
  }
  if (password.trim() !== password) {
    return "Password must not start or end with whitespace";
  }
  if (!/[a-z]/.test(password)) return "Password must include a lowercase letter";
  if (!/[A-Z]/.test(password)) return "Password must include an uppercase letter";
  if (!/\d/.test(password)) return "Password must include a number";
  if (!/[^A-Za-z0-9]/.test(password)) {
    return "Password must include a special character";
  }
  const lowered = password.toLowerCase();
  const username = opts?.username?.toLowerCase() ?? "";
  const emailLocal = opts?.email?.toLowerCase().split("@")[0] ?? "";
  for (const fragment of [username, emailLocal]) {
    if (fragment.length >= 3 && lowered.includes(fragment)) {
      return "Password must not contain your username or email";
    }
  }
  return null;
}
