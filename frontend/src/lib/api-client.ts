// Thin API client wrapper around the FastAPI backend.
// All backend calls should route through this module (or src/services/)
// so base URL + auth headers are applied in one place.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      // TODO: attach Authorization: Bearer <token> from session storage.
      ...(options?.headers ?? {}),
    },
    ...options,
  });

  if (!res.ok) {
    throw new Error(`API error ${res.status} on ${path}`);
  }
  return (await res.json()) as T;
}
