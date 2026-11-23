import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Member, MemberSettlementPreview } from "@/lib/api";

import MemberSettlementPanel from ".";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getMemberSettlement: vi.fn(),
    settleMemberExit: vi.fn(),
    markSettlementPaid: vi.fn(),
  };
});

import { getMemberSettlement, markSettlementPaid, settleMemberExit } from "@/lib/api";

const exited = {
  id: "member-2",
  psn: "0002",
  name: "Ada Obi",
  status: "non_financial",
  loan_restricted: false,
  membership_exit_date: "2026-10-31",
  membership_exit_reason: "Relocated",
} as unknown as Member;

const preview = (
  overrides: Partial<MemberSettlementPreview> = {}
): MemberSettlementPreview => ({
  member_id: exited.id,
  savings_balance: "5000.00",
  active_loan_count: 1,
  active_loan_outstanding: "800.00",
  settlement: null,
  ...overrides,
});

const pendingSettlement = {
  id: "settlement-1",
  member_id: exited.id,
  settled_on: "2026-11-01",
  savings_balance: "5000.00",
  offset_total: "800.00",
  payout_amount: "4200.00",
  payout_status: "pending" as const,
  paid_on: null,
  paid_reference: null,
  note: null,
  allocations: [{ loan_id: "loan-1", amount: "800.00", loan_type_name: "Capital Loan" }],
};

beforeEach(() => {
  vi.mocked(getMemberSettlement).mockReset();
  vi.mocked(settleMemberExit).mockReset();
  vi.mocked(markSettlementPaid).mockReset();
});

describe("MemberSettlementPanel", () => {
  it("does nothing for a member who has not exited", () => {
    const { container } = render(
      <MemberSettlementPanel
        member={{ ...exited, membership_exit_date: null } as Member}
        canView
        canSettle
      />
    );
    expect(container).toBeEmptyDOMElement();
    expect(getMemberSettlement).not.toHaveBeenCalled();
  });

  it("stays hidden without the savings view permission", () => {
    const { container } = render(
      <MemberSettlementPanel member={exited} canView={false} canSettle={false} />
    );
    expect(container).toBeEmptyDOMElement();
    expect(getMemberSettlement).not.toHaveBeenCalled();
  });

  it("shows the offset preview and settles the exit", async () => {
    vi.mocked(getMemberSettlement).mockResolvedValueOnce(preview());
    vi.mocked(getMemberSettlement).mockResolvedValueOnce(
      preview({ savings_balance: "0.00", settlement: pendingSettlement })
    );
    vi.mocked(settleMemberExit).mockResolvedValueOnce(pendingSettlement);

    render(<MemberSettlementPanel member={exited} canView canSettle />);

    expect(await screen.findByText("₦5,000.00")).toBeInTheDocument();
    expect(screen.getByText(/₦800\.00 \(1 loan\)/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Settle exit" }));
    await userEvent.type(screen.getByLabelText("Settlement note"), "Final month confirmed");
    await userEvent.click(screen.getByRole("button", { name: "Settle savings" }));

    await waitFor(() =>
      expect(settleMemberExit).toHaveBeenCalledWith(
        exited.id,
        expect.objectContaining({ note: "Final month confirmed", settled_on: expect.any(String) })
      )
    );
    // Reloaded after settling: the panel now shows the recorded payout.
    expect(await screen.findByText("Pending")).toBeInTheDocument();
    expect(screen.getByText(/Capital Loan — ₦800\.00/)).toBeInTheDocument();
  });

  it("withholds the actions from an officer who may only view", async () => {
    vi.mocked(getMemberSettlement).mockResolvedValueOnce(preview());

    render(<MemberSettlementPanel member={exited} canView canSettle={false} />);

    expect(await screen.findByText("₦5,000.00")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Settle exit" })).not.toBeInTheDocument();
    expect(
      screen.getByText(/Only an officer with the savings settlement permission/)
    ).toBeInTheDocument();
  });

  it("records a pending payout as paid only with a reference", async () => {
    vi.mocked(getMemberSettlement).mockResolvedValueOnce(
      preview({ savings_balance: "0.00", settlement: pendingSettlement })
    );
    vi.mocked(markSettlementPaid).mockResolvedValueOnce({
      ...pendingSettlement,
      payout_status: "paid",
      paid_on: "2026-11-15",
      paid_reference: "CASH 0421",
    });
    vi.mocked(getMemberSettlement).mockResolvedValueOnce(
      preview({
        savings_balance: "0.00",
        settlement: {
          ...pendingSettlement,
          payout_status: "paid",
          paid_on: "2026-11-15",
          paid_reference: "CASH 0421",
        },
      })
    );

    render(<MemberSettlementPanel member={exited} canView canSettle />);

    await userEvent.click(await screen.findByRole("button", { name: "Mark payout paid" }));

    const submit = screen.getByRole("button", { name: "Record payout" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Payment reference"), "CASH 0421");
    await userEvent.click(submit);

    await waitFor(() =>
      expect(markSettlementPaid).toHaveBeenCalledWith(
        exited.id,
        expect.objectContaining({ reference: "CASH 0421" })
      )
    );
    expect(await screen.findByText("CASH 0421")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark payout paid" })).not.toBeInTheDocument();
  });
});
