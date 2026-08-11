/** API base URL for fetch calls. Prefer same-origin + Next.js rewrite in production. */
export function getApiBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (explicit) return explicit;

  // Vercel: set API_BASE_URL (server) — browser calls /api/... via rewrite proxy.
  if (process.env.NODE_ENV === "production") return "";

  return "http://localhost:8000";
}
