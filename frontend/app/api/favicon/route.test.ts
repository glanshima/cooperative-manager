import { describe, expect, it, vi } from "vitest";

import { GET } from "./route";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("GET /api/favicon", () => {
  it("streams the uploaded logo with its own content type", async () => {
    const bytes = new Uint8Array([137, 80, 78, 71]);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({ logo_url: "https://blob.example/logo.png" }))
      .mockResolvedValueOnce(
        new Response(bytes, { status: 200, headers: { "content-type": "image/png" } })
      );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("https://app.example/api/favicon"));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/branding$/);
    expect(fetchMock.mock.calls[1][0]).toBe("https://blob.example/logo.png");
  });

  it("falls back to the static icon when no logo is uploaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ logo_url: null })));

    const response = await GET(new Request("https://app.example/api/favicon"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.example/icons/favicon.svg");
  });

  it("falls back to the static icon when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch")));

    const response = await GET(new Request("https://app.example/api/favicon"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.example/icons/favicon.svg");
  });
});
