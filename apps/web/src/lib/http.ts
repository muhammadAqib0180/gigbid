// Typed API access. `paths` comes from src/lib/api/schema.d.ts, generated from FastAPI's OpenAPI schema
// (`npm run gen:api`) - never edited by hand.
import createClient from "openapi-fetch";
import type { components, paths } from "./api/schema";

export const api = createClient<paths>({ baseUrl: "", credentials: "include" });
export type Schemas = components["schemas"];

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Unwrap an openapi-fetch result: throw ApiError on failure so pages can render error states. */
export async function must<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || data === undefined) {
    const detail = (error as { detail?: unknown })?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return data;
}

export const fmtMoney = (n?: number | null, unit?: string | null) =>
  n == null ? "-" : `$${Math.round(n).toLocaleString()}${unit === "hourly" ? "/h" : ""}`;
export const pct = (n?: number | null) => (n == null ? "-" : `${Math.round(n * 100)}%`);
export const enc = (s: string) => encodeURIComponent(s);
