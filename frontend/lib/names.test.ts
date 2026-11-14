import { describe, expect, it } from "vitest";

import { lastNameFirst } from "./names";

describe("lastNameFirst", () => {
  it("moves the final word in front of the rest", () => {
    expect(lastNameFirst("Ada Obi")).toBe("Obi, Ada");
    expect(lastNameFirst("Ada Ngozi Obi")).toBe("Obi, Ada N.");
  });

  it("abbreviates middle names after the first given name", () => {
    expect(lastNameFirst("Ada Ngozi Chika Obi")).toBe("Obi, Ada N. C.");
    expect(lastNameFirst("Ada Obi")).toBe("Obi, Ada");
  });

  it("keeps names that already carry a comma as written", () => {
    expect(lastNameFirst("Obi, Ada")).toBe("Obi, Ada");
  });

  it("leaves a single-word name and trims surrounding space", () => {
    expect(lastNameFirst("Madonna")).toBe("Madonna");
    expect(lastNameFirst("  Ada Obi  ")).toBe("Obi, Ada");
  });

  it("has nothing to show for a missing name", () => {
    expect(lastNameFirst(null)).toBeNull();
    expect(lastNameFirst("   ")).toBeNull();
  });
});
