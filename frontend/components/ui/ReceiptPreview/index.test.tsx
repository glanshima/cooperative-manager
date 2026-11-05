import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ReceiptPreview from "./index";

describe("ReceiptPreview", () => {
  it("renders an image inline for image content types", () => {
    render(<ReceiptPreview contentType="image/png" base64="abc123" />);

    const image = screen.getByRole("img", { name: "Payment receipt" });
    expect(image).toHaveAttribute("src", "data:image/png;base64,abc123");
  });

  it("renders a download link for non-image content types", () => {
    render(<ReceiptPreview contentType="application/pdf" base64="xyz789" />);

    const link = screen.getByRole("link", { name: "Download receipt (PDF)" });
    expect(link).toHaveAttribute("href", "data:application/pdf;base64,xyz789");
    expect(link).toHaveAttribute("download", "receipt");
  });
});
