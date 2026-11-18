import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AuthShell from ".";

describe("AuthShell", () => {
  it("leads with the cooperative identity and keeps the platform credit secondary", () => {
    render(
      <AuthShell>
        <h1>Log in</h1>
      </AuthShell>
    );

    expect(screen.getByText("MACT Cooperative")).toBeInTheDocument();
    expect(screen.getByText("Powered by")).toBeInTheDocument();
    expect(screen.getByText("Koperra")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
  });
});
