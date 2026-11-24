import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CashbookAccount } from "@/lib/api";

import { JournalLineDraft, emptyJournal } from "../journal";
import JournalLinesEditor from "./index";

const ACCOUNTS: CashbookAccount[] = [
  {
    id: "bank",
    code: "1010",
    name: "Bank",
    kind: "asset",
    is_active: true,
  },
  {
    id: "income",
    code: "4000",
    name: "Interest income",
    kind: "income",
    is_active: true,
  },
];

function Harness({ initial }: { initial: JournalLineDraft[] }) {
  const [lines, setLines] = useState(initial);
  return <JournalLinesEditor accounts={ACCOUNTS} lines={lines} onChange={setLines} />;
}

describe("JournalLinesEditor", () => {
  it("keeps a line on one side: typing a debit clears its credit", async () => {
    const user = userEvent.setup();
    const lines = emptyJournal();
    lines[0] = { ...lines[0], accountId: "bank", credit: "250" };
    render(<Harness initial={lines} />);

    await user.type(screen.getByLabelText("Line 1 debit"), "250");

    expect(screen.getByLabelText("Line 1 debit")).toHaveValue("250");
    expect(screen.getByLabelText("Line 1 credit")).toHaveValue("");
  });

  it("reports the entry as balanced once both sides match", async () => {
    const user = userEvent.setup();
    const lines = emptyJournal();
    lines[0] = { ...lines[0], accountId: "bank" };
    lines[1] = { ...lines[1], accountId: "income" };
    render(<Harness initial={lines} />);

    expect(screen.getByText(/Out by/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Line 1 debit"), "100");
    await user.type(screen.getByLabelText("Line 2 credit"), "100");

    expect(screen.getByText("Balanced")).toBeInTheDocument();
  });

  it("only removes a line once there are more than two", async () => {
    const user = userEvent.setup();
    render(<Harness initial={emptyJournal()} />);

    expect(screen.getAllByRole("button", { name: "Remove" })[0]).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Add line" }));
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(3);

    await user.click(screen.getAllByRole("button", { name: "Remove" })[2]);
    expect(screen.getAllByLabelText(/account$/)).toHaveLength(2);
  });
});
