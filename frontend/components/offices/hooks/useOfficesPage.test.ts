import { act, renderHook, waitFor } from "@testing-library/react";
import type { FormEvent } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createOffice, listOffices, updateOffice } from "@/lib/api";
import type { Office } from "@/lib/api";

import { useOfficesPage } from "./useOfficesPage";

vi.mock("@/lib/api", () => ({
  listOffices: vi.fn(),
  createOffice: vi.fn(),
  updateOffice: vi.fn(),
}));

const listOfficesMock = vi.mocked(listOffices);
const createOfficeMock = vi.mocked(createOffice);
const updateOfficeMock = vi.mocked(updateOffice);

const office: Office = {
  id: "office-1",
  name: "Treasurer",
  description: "Finance",
  is_active: true,
  created_at: "2026-11-01T00:00:00Z",
};

const logout = vi.fn();

function submitEvent() {
  return { preventDefault: vi.fn() } as unknown as FormEvent;
}

describe("useOfficesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listOfficesMock.mockResolvedValue([office]);
    createOfficeMock.mockResolvedValue(office);
    updateOfficeMock.mockResolvedValue({ ...office, is_active: false });
  });

  it("loads offices once auth has settled", async () => {
    const { result } = renderHook(() => useOfficesPage(false, logout));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(listOfficesMock).toHaveBeenCalledTimes(1);
    expect(result.current.table.items).toEqual([office]);
    expect(result.current.feedback.error).toBeNull();
  });

  it("creates an office and resets the form", async () => {
    const { result } = renderHook(() => useOfficesPage(false, logout));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.form.setName("President");
      result.current.form.setDescription("Chair");
    });

    await act(async () => {
      await result.current.form.submit(submitEvent());
    });

    expect(createOfficeMock).toHaveBeenCalledWith({
      name: "President",
      description: "Chair",
    });
    expect(result.current.form.name).toBe("");
    expect(result.current.form.description).toBe("");
    expect(listOfficesMock).toHaveBeenCalledTimes(2);
  });

  it("toggles an office's active flag and refreshes the list", async () => {
    const { result } = renderHook(() => useOfficesPage(false, logout));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.table.onToggleActive(office);
    });

    expect(updateOfficeMock).toHaveBeenCalledWith("office-1", { is_active: false });
    expect(listOfficesMock).toHaveBeenCalledTimes(2);
  });

  it("surfaces load failures through feedback", async () => {
    listOfficesMock.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useOfficesPage(false, logout));

    await waitFor(() => expect(result.current.feedback.error).toBe("network down"));
    expect(result.current.loading).toBe(false);
  });
});
