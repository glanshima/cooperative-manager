import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DeductionsPageModel } from "../hooks/useDeductionsPage";
import DeductionFilters from "./index";

function renderFilters({ search = "", resultCount = 2 } = {}) {
  const setSearch = vi.fn();
  const filters = {
    month: "2026-11",
    setMonth: vi.fn(),
    status: "all",
    setStatus: vi.fn(),
    search,
    setSearch,
  } as unknown as DeductionsPageModel["filters"];

  render(
    <DeductionFilters
      filters={filters}
      totals={{
        contribution_total: "2000.00",
        loan_total: "1000.00",
        arrears_total: "0.00",
        other_total: "0.00",
        grand_total: "3000.00",
      }}
      resultCount={resultCount}
      onCreate={vi.fn()}
      onPrint={vi.fn()}
    />
  );
  return { setSearch };
}

describe("DeductionFilters search", () => {
  it("labels the ledger search field and sends the term", async () => {
    const user = userEvent.setup();
    const { setSearch } = renderFilters({ search: "" });

    const field = screen.getByLabelText(
      "Search ledger by name, PSN, payroll reference or note"
    );
    await user.type(field, "P");
    expect(setSearch).toHaveBeenLastCalledWith("P");

    // Nothing to clear until a term is present.
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
  });

  it("clears the search from a labelled action", async () => {
    const user = userEvent.setup();
    const { setSearch } = renderFilters({ search: "ada" });

    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(setSearch).toHaveBeenCalledWith("");
  });

  it("announces the filtered count while keeping the month totals distinct", () => {
    renderFilters({ search: "ada", resultCount: 2 });

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/2 records match “ada”/);
    expect(status).toHaveTextContent(/month totals above include every record/);
    // The month-wide total is still on screen.
    expect(screen.getByText(/3,000\.00/)).toBeInTheDocument();
  });
});
