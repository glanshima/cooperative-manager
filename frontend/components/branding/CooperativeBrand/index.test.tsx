import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { getBranding } from "@/lib/api";
import BrandingProvider from "../BrandingProvider";

import CooperativeBrand from ".";

vi.mock("@/lib/api", () => ({
  getBranding: vi.fn(),
}));

const getBrandingMock = vi.mocked(getBranding);

describe("CooperativeBrand", () => {
  it("uses the deployment defaults when there is no branding context", () => {
    render(<CooperativeBrand />);

    expect(screen.getByText("MACT Cooperative")).toBeInTheDocument();
    expect(screen.getByText("M")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("renders the configured logo instead of the monogram", async () => {
    getBrandingMock.mockResolvedValue({
      cooperative_name: "Riverside Cooperative",
      cooperative_short_name: "Riverside",
      cooperative_monogram: "RC",
      logo_url: "https://blob.example/riverside.png",
    });

    render(
      <BrandingProvider>
        <CooperativeBrand />
      </BrandingProvider>
    );

    expect(await screen.findByText("Riverside Cooperative")).toBeInTheDocument();
    expect(document.querySelector("img")).toHaveAttribute(
      "src",
      "https://blob.example/riverside.png"
    );
    expect(screen.queryByText("RC")).not.toBeInTheDocument();
  });

  it("honours explicit props over the provider values", async () => {
    getBrandingMock.mockResolvedValue({
      cooperative_name: "Riverside Cooperative",
      cooperative_short_name: "Riverside",
      cooperative_monogram: "RC",
      logo_url: "https://blob.example/riverside.png",
    });

    render(
      <BrandingProvider>
        <CooperativeBrand name="Preview Name" monogram="P" logoUrl={null} />
      </BrandingProvider>
    );

    expect(await screen.findByText("Preview Name")).toBeInTheDocument();
    expect(screen.getByText("P")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
