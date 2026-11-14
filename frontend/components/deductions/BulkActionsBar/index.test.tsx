import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DeductionActionKind } from "../hooks/useDeductionsPage";
import BulkActionsBar from "./index";

function renderBar(
  eligible: Partial<Record<DeductionActionKind, number>> = {},
  count = 13
) {
  const onAction = vi.fn();
  render(
    <BulkActionsBar
      count={count}
      eligible={
        {
          submit: count,
          return_to_draft: 0,
          confirm: count,
          not_deducted: count,
          void: count,
          ...eligible,
        } as Record<DeductionActionKind, number>
      }
      busy={false}
      onAction={onAction}
      onClear={vi.fn()}
    />
  );
  return { onAction };
}

describe("BulkActionsBar eligibility", () => {
  it("shows how many of the selection each action can reach", () => {
    renderBar({ confirm: 5 });

    expect(screen.getByText("13 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm (5)" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Submit" })).toBeEnabled();
  });

  it("disables an action no selected row can reach and says which state it needs", () => {
    renderBar({ confirm: 0 });

    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute("title", "Only submitted deductions can be confirmed.");
  });

  it("sends the chosen action with the selection untouched", async () => {
    const user = userEvent.setup();
    const { onAction } = renderBar({ confirm: 5 });

    await user.click(screen.getByRole("button", { name: "Confirm (5)" }));
    expect(onAction).toHaveBeenCalledWith("confirm");
  });
});
