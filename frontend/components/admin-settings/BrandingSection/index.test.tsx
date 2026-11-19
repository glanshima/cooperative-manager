import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { deleteLogo, uploadLogo } from "@/lib/api";
import type { Settings } from "@/lib/api";

import BrandingSection from ".";
import type { SettingsPageModel } from "../hooks/useSettingsPage";

vi.mock("@/lib/api", () => ({
  uploadLogo: vi.fn(),
  deleteLogo: vi.fn(),
}));

const uploadLogoMock = vi.mocked(uploadLogo);
const deleteLogoMock = vi.mocked(deleteLogo);

const settings: Settings = {
  id: "settings-1",
  loan_restriction_behavior: "warn",
  loan_form_fee: "50.00",
  members_module_enabled: true,
  loans_module_enabled: true,
  deductions_module_enabled: true,
  cashbook_module_enabled: false,
  dividends_module_enabled: false,
  cooperative_name: "MACT Cooperative",
  cooperative_short_name: "MACT",
  cooperative_monogram: "M",
  logo_url: null,
};

function pngFile(name = "logo.png", bytes: number[] = [0x89, 0x50, 0x4e, 0x47]): File {
  return new File([new Uint8Array(bytes)], name, { type: "image/png" });
}

// The real section edits a controlled copy of settings; a spy that never
// feeds the new value back would swallow every keystroke.
function EditableSection() {
  const [value, setValue] = useState(settings);
  const setField: SettingsPageModel["setField"] = (key, next) =>
    setValue((current) => ({ ...current, [key]: next }));
  return <BrandingSection settings={value} setField={setField} />;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("BrandingSection", () => {
  it("edits the cooperative name, short name and monogram", async () => {
    const user = userEvent.setup();
    render(<EditableSection />);

    expect(screen.getByLabelText("Cooperative name")).toHaveValue("MACT Cooperative");
    expect(screen.getByLabelText("Short name")).toHaveValue("MACT");
    expect(screen.getByLabelText("Monogram")).toHaveValue("M");

    await user.clear(screen.getByLabelText("Cooperative name"));
    await user.type(screen.getByLabelText("Cooperative name"), "Riverside");
    await user.clear(screen.getByLabelText("Short name"));
    await user.type(screen.getByLabelText("Short name"), "RC");
    await user.clear(screen.getByLabelText("Monogram"));
    await user.type(screen.getByLabelText("Monogram"), "R");

    expect(screen.getByLabelText("Cooperative name")).toHaveValue("Riverside");
    expect(screen.getByLabelText("Short name")).toHaveValue("RC");
    expect(screen.getByLabelText("Monogram")).toHaveValue("R");
  });

  it("shows the monogram until a logo is stored", () => {
    render(<BrandingSection settings={settings} setField={vi.fn()} />);

    expect(screen.getByText("No logo uploaded")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Cooperative logo preview" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove logo" })).not.toBeInTheDocument();
  });

  it("rejects a file over the 1 MB limit before uploading", () => {
    const setField = vi.fn();
    render(<BrandingSection settings={settings} setField={setField} />);

    fireEvent.change(screen.getByLabelText("Choose a logo image"), {
      target: { files: [pngFile("large.png", new Array(1_000_001).fill(0))] },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("1 MB or smaller");
    expect(uploadLogoMock).not.toHaveBeenCalled();
  });

  it("rejects a file type outside the raster formats", () => {
    render(<BrandingSection settings={settings} setField={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Choose a logo image"), {
      target: {
        files: [new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" })],
      },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("PNG, JPEG or WebP");
    expect(uploadLogoMock).not.toHaveBeenCalled();
  });

  it("uploads the chosen file as base64 and shows the new logo", async () => {
    const user = userEvent.setup();
    const setField = vi.fn();
    uploadLogoMock.mockResolvedValue({
      ...settings,
      logo_url: "https://blob.example/new-logo.png",
    });
    render(<BrandingSection settings={settings} setField={setField} />);

    await user.upload(screen.getByLabelText("Choose a logo image"), pngFile());
    await user.click(screen.getByRole("button", { name: "Upload logo" }));

    await waitFor(() => expect(uploadLogoMock).toHaveBeenCalledTimes(1));
    const [contentType, base64] = uploadLogoMock.mock.calls[0];
    expect(contentType).toBe("image/png");
    expect(base64).toMatch(/^iVBOR/); // base64 of the PNG signature
    expect(base64).not.toContain("data:");

    expect(setField).toHaveBeenCalledWith("logo_url", "https://blob.example/new-logo.png");
    expect(await screen.findByRole("status")).toHaveTextContent("Logo updated");
  });

  it("reports a failed upload without clearing the form", async () => {
    const user = userEvent.setup();
    uploadLogoMock.mockRejectedValue(
      new Error("Logo storage is not configured for this deployment.")
    );
    render(<BrandingSection settings={settings} setField={vi.fn()} />);

    await user.upload(screen.getByLabelText("Choose a logo image"), pngFile());
    await user.click(screen.getByRole("button", { name: "Upload logo" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logo storage is not configured"
    );
    expect(screen.getByRole("button", { name: "Upload logo" })).toBeEnabled();
  });

  it("removes the stored logo", async () => {
    const user = userEvent.setup();
    const setField = vi.fn();
    deleteLogoMock.mockResolvedValue({ ...settings, logo_url: null });
    render(
      <BrandingSection
        settings={{ ...settings, logo_url: "https://blob.example/old-logo.png" }}
        setField={setField}
      />
    );

    expect(screen.getByRole("img", { name: "Cooperative logo preview" })).toHaveAttribute(
      "src",
      "https://blob.example/old-logo.png"
    );

    await user.click(screen.getByRole("button", { name: "Remove logo" }));

    await waitFor(() => expect(deleteLogoMock).toHaveBeenCalledTimes(1));
    expect(setField).toHaveBeenCalledWith("logo_url", null);
    expect(await screen.findByRole("status")).toHaveTextContent("Logo removed");
  });
});
