import { describe, expect, it, vi } from "vitest";

import { getBranding } from "./branding";
import { deleteLogo, uploadLogo } from "./settings";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("branding endpoints", () => {
  it("reads the public branding slice", async () => {
    const branding = {
      cooperative_name: "MACT Cooperative",
      cooperative_short_name: "MACT",
      cooperative_monogram: "M",
      logo_url: null,
    };
    const fetchMock = vi.fn().mockResolvedValue(response(branding));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBranding()).resolves.toEqual(branding);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(new URL(url).pathname).toBe("/api/branding");
  });

  it("uploads the logo as base64 JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ id: "settings-1" }));
    vi.stubGlobal("fetch", fetchMock);

    await uploadLogo("image/png", "iVBORw0KGgo=");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url).pathname).toBe("/api/settings/logo");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      content_type: "image/png",
      image_base64: "iVBORw0KGgo=",
    });
  });

  it("removes the logo with a DELETE", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ id: "settings-1", logo_url: null }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteLogo()).resolves.toMatchObject({ logo_url: null });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url).pathname).toBe("/api/settings/logo");
    expect(init.method).toBe("DELETE");
  });
});
