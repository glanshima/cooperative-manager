import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getRepayment, listAllRepayments, verifyRepayment } from "@/lib/api";
import type { LoanRepayment } from "@/lib/api";

import { useLoanRepaymentsPage } from "./useLoanRepaymentsPage";

vi.mock("@/lib/api", () => ({
  listAllRepayments: vi.fn(),
  getRepayment: vi.fn(),
  verifyRepayment: vi.fn(),
}));

const listMock = vi.mocked(listAllRepayments);
const getMock = vi.mocked(getRepayment);
const verifyMock = vi.mocked(verifyRepayment);

const repayment = {
  id: "rep-1",
  loan_id: "loan-1",
  member_id: "member-1",
  member_name: "Ada Obi",
  amount_claimed: "1000.00",
  status: "awaiting_verification",
} as unknown as LoanRepayment;

const logout = vi.fn();

async function renderLoadedHook() {
  const rendered = renderHook(() => useLoanRepaymentsPage(false, logout));
  await waitFor(() => expect(rendered.result.current.loading).toBe(false));
  return rendered;
}

describe("useLoanRepaymentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue([repayment]);
    getMock.mockResolvedValue({ ...repayment } as any);
    verifyMock.mockResolvedValue(repayment);
    window.history.replaceState(null, "", "/");
  });

  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("loads the full repayment history by default", async () => {
    const { result } = await renderLoadedHook();

    expect(listMock).toHaveBeenCalledWith(undefined);
    expect(result.current.filter.awaitingOnly).toBe(false);
    expect(result.current.table.items).toEqual([repayment]);
  });

  it("opens on awaiting verification when the dashboard links here", async () => {
    window.history.replaceState(
      null,
      "",
      "/admin/loan-repayments?status=awaiting_verification"
    );
    const { result } = await renderLoadedHook();

    expect(listMock).toHaveBeenCalledWith("awaiting_verification");
    expect(result.current.filter.awaitingOnly).toBe(true);
  });

  it("clears the preset and reloads the history", async () => {
    window.history.replaceState(
      null,
      "",
      "/admin/loan-repayments?status=awaiting_verification"
    );
    const { result } = await renderLoadedHook();

    act(() => result.current.filter.clear());

    await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(undefined));
    expect(result.current.filter.awaitingOnly).toBe(false);
  });
});
