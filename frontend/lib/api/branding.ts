import { apiFetch } from "./client";

/** The public slice of settings a signed-out screen may render. */
export interface Branding {
  cooperative_name: string;
  cooperative_short_name: string;
  cooperative_monogram: string;
  logo_url: string | null;
}

export async function getBranding(): Promise<Branding> {
  return apiFetch<Branding>("/api/branding");
}
