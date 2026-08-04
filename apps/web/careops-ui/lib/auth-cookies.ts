// Client-side cookie helpers for the careops_token JWT.
// The cookie is NOT httpOnly so the browser JS can read it for API calls,
// and the Next.js Proxy can also read it for route protection.
// Phase 6 (cloud deploy) will replace this with a server-side session.

const COOKIE_NAME = "careops_token";
const MAX_AGE = 60 * 60 * 24 * 7; // 7 days

export function setAuthCookie(token: string): void {
  document.cookie = `${COOKIE_NAME}=${token}; path=/; max-age=${MAX_AGE}; SameSite=Lax`;
}

export function getAuthToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function clearAuthCookie(): void {
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
}
