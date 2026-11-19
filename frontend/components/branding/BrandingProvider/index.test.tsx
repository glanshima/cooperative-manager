import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getBranding } from "@/lib/api";
import BrandingProvider, { useBranding } from ".";

vi.mock("@/lib/api", () => ({
  getBranding: vi.fn(),
}));

const getBrandingMock = vi.mocked(getBranding);

function Probe() {
  const { branding, setBranding } = useBranding();
  return (
    <>
      <span data-testid="name">{branding.cooperative_name}</span>
      <span data-testid="short-name">{branding.cooperative_short_name}</span>
      <span data-testid="monogram">{branding.cooperative_monogram}</span>
      <button type="button" onClick={() => setBranding({ cooperative_name: "Riverside" })}>
        Rename
      </button>
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BrandingProvider", () => {
  it("shows the deployment defaults before the fetch settles", () => {
    getBrandingMock.mockReturnValue(new Promise(() => {}));
    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>
    );

    expect(screen.getByTestId("name")).toHaveTextContent("MACT Cooperative");
    expect(screen.getByTestId("short-name")).toHaveTextContent("MACT");
    expect(screen.getByTestId("monogram")).toHaveTextContent("M");
  });

  it("replaces the defaults with the stored cooperative identity", async () => {
    getBrandingMock.mockResolvedValue({
      cooperative_name: "Riverside Cooperative",
      cooperative_short_name: "Riverside",
      cooperative_monogram: "RC",
      logo_url: "https://blob.example/riverside.png",
    });
    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>
    );

    expect(await screen.findByText("Riverside Cooperative")).toBeInTheDocument();
    expect(screen.getByTestId("short-name")).toHaveTextContent("Riverside");
    expect(screen.getByTestId("monogram")).toHaveTextContent("RC");
  });

  it("keeps the defaults when branding cannot be loaded", async () => {
    getBrandingMock.mockRejectedValue(new Error("offline"));
    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>
    );

    await vi.waitFor(() => expect(getBrandingMock).toHaveBeenCalled());
    expect(screen.getByTestId("name")).toHaveTextContent("MACT Cooperative");
  });

  it("lets settings updates repaint the brand without a reload", async () => {
    const user = userEvent.setup();
    getBrandingMock.mockResolvedValue({
      cooperative_name: "MACT Cooperative",
      cooperative_short_name: "MACT",
      cooperative_monogram: "M",
      logo_url: null,
    });
    render(
      <BrandingProvider>
        <Probe />
      </BrandingProvider>
    );

    await user.click(screen.getByRole("button", { name: "Rename" }));

    expect(screen.getByTestId("name")).toHaveTextContent("Riverside");
  });

  it("falls back to the defaults outside a provider", () => {
    render(<Probe />);

    expect(screen.getByTestId("name")).toHaveTextContent("MACT Cooperative");
  });
});
