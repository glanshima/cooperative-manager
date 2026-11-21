import { NextResponse } from "next/server";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * The tab icon is resolved per request rather than at build time, because the
 * logo it should show is uploaded from Settings long after the frontend was
 * deployed. Falls back to the static Koperra icon when no logo is set.
 */
export async function GET(request: Request) {
  try {
    const brandingRes = await fetch(`${API_URL}/api/branding`, { cache: "no-store" });
    if (brandingRes.ok) {
      const branding = (await brandingRes.json()) as { logo_url?: string | null };
      if (branding.logo_url) {
        const logoRes = await fetch(branding.logo_url, { cache: "no-store" });
        if (logoRes.ok && logoRes.body) {
          return new NextResponse(logoRes.body, {
            headers: {
              "content-type": logoRes.headers.get("content-type") ?? "image/png",
              "cache-control": "public, max-age=300",
            },
          });
        }
      }
    }
  } catch {
    // Backend unreachable: the static icon is still a valid answer.
  }

  return NextResponse.redirect(new URL("/icons/favicon.svg", request.url), {
    headers: { "cache-control": "public, max-age=60" },
  });
}
