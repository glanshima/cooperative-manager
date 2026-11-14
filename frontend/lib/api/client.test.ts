import { describe, expect, it, vi } from "vitest";

import { createOffice, listAuditEvents, listOffices, revokeRole } from "./admin";
import { ApiError, setToken } from "./client";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("apiFetch", () => {
  it("attaches the bearer token and serializes only defined search params", async () => {
    setToken("token-123");
    const fetchMock = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);

    await listAuditEvents({ entity_type: "member", event_type: undefined });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    const parsed = new URL(url as string);
    expect(parsed.pathname).toBe("/api/audit");
    expect(parsed.searchParams.get("entity_type")).toBe("member");
    expect(parsed.searchParams.has("event_type")).toBe(false);
    expect((init as RequestInit).headers).toMatchObject({
      Authorization: "Bearer token-123",
    });
    expect((init as RequestInit).cache).toBe("no-store");
  });

  it("sends JSON bodies with a content-type header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ id: "o1" }));
    vi.stubGlobal("fetch", fetchMock);

    await createOffice({ name: "Treasurer", description: "Finance" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ name: "Treasurer", description: "Finance" }));
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("turns a structured detail into a readable ApiError message", async () => {
    const detail = {
      error: "member_conflict",
      message: "You cannot review your own loan application.",
      eligible_approvers: ["u2"],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail }, 409)));

    let error: unknown;
    try {
      await listOffices();
    } catch (e) {
      error = e;
    }

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("You cannot review your own loan application.");
    expect((error as ApiError).detail).toEqual(detail);
  });

  it("replaces a rejected fetch with an actionable transport message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    let error: unknown;
    try {
      await listOffices();
    } catch (e) {
      error = e;
    }

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).transport).toBe(true);
    expect((error as ApiError).message).toContain("Could not reach the server");
    expect((error as ApiError).message).not.toContain("Failed to fetch");
  });

  it("falls back to a status message when detail is missing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, 500)));

    await expect(listOffices()).rejects.toThrow("Request failed with status 500");
  });

  it("returns undefined for 204 responses without parsing a body", async () => {
    const json = vi.fn(() => {
      throw new Error("a 204 response must not be parsed as JSON");
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json } as unknown as Response)
    );

    await expect(revokeRole("user-1", "assignment-1")).resolves.toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });
});
