import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { LoanApplicationsPageModel } from "../hooks/useLoanApplicationsPage";

import LoanApplicationsView from "./index";

vi.mock("../ApplicationsTable", () => ({ default: () => null }));
vi.mock("../ApplicationReviewPanel", () => ({ default: () => null }));

function makeModel(current: LoanApplicationsPageModel["filter"]["current"] = "pending") {
  const set = vi.fn();
  const clear = vi.fn();
  const model = {
    loading: false,
    filter: { current, set, clear },
    feedback: { error: null },
    table: {},
    review: {},
  } as unknown as LoanApplicationsPageModel;
  return { model, set, clear };
}

describe("LoanApplicationsView", () => {
  it("offers the five admin views and defaults to Pending", async () => {
    const user = userEvent.setup();
    const { model, set } = makeModel();

    render(<LoanApplicationsView model={model} />);

    expect(screen.getByRole("button", { name: "Pending" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(
      screen.getByRole("button", { name: "Approved / awaiting disbursement" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rejected" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelled" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rejected" }));
    expect(set).toHaveBeenCalledWith("rejected");
  });

  it("keeps dashboard queue presets visible and dismissible", async () => {
    const user = userEvent.setup();
    const { model, clear } = makeModel("review");

    render(<LoanApplicationsView model={model} />);

    expect(screen.getByText("Showing applications awaiting review.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all" }));
    expect(clear).toHaveBeenCalledOnce();
  });
});
