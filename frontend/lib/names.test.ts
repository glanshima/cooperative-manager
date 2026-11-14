import { describe, expect, it } from "vitest";

import { lastNameFirst, splitStoredName, userDisplayName } from "./names";

describe("lastNameFirst", () => {
  it("moves the final word in front of the rest", () => {
    expect(lastNameFirst("Ada Obi")).toBe("Obi, Ada");
    expect(lastNameFirst("Ada Ngozi Obi")).toBe("Obi, Ada N.");
  });

  it("abbreviates middle names after the first given name", () => {
    expect(lastNameFirst("Ada Ngozi Chika Obi")).toBe("Obi, Ada N. C.");
    expect(lastNameFirst("Ada Obi")).toBe("Obi, Ada");
  });

  it("abbreviates other names in an already printed Last, First form", () => {
    expect(lastNameFirst("Okafor, Adaeze")).toBe("Okafor, Adaeze");
    expect(lastNameFirst("Okafor, Adaeze Ngozi")).toBe("Okafor, Adaeze N.");
    expect(lastNameFirst("Okafor, Adaeze Ngozi Chika")).toBe("Okafor, Adaeze N. C.");
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

describe("splitStoredName", () => {
  it("splits the printed Last, First Other(s) form", () => {
    expect(splitStoredName("Okafor, Adaeze Ngozi Chika")).toEqual({
      last_name: "Okafor",
      first_name: "Adaeze",
      other_names: "Ngozi Chika",
    });
    expect(splitStoredName("Okafor, Adaeze")).toEqual({
      last_name: "Okafor",
      first_name: "Adaeze",
      other_names: "",
    });
  });

  it("splits a legacy given-name-first record", () => {
    expect(splitStoredName("Ada Ngozi Obi")).toEqual({
      last_name: "Obi",
      first_name: "Ada",
      other_names: "Ngozi",
    });
    expect(splitStoredName("Ada Obi")).toEqual({
      last_name: "Obi",
      first_name: "Ada",
      other_names: "",
    });
  });

  it("keeps a single word as the family name", () => {
    expect(splitStoredName("Madonna")).toEqual({
      last_name: "Madonna",
      first_name: "",
      other_names: "",
    });
  });

  it("returns empty parts for a missing name", () => {
    expect(splitStoredName(null)).toEqual({ last_name: "", first_name: "", other_names: "" });
    expect(splitStoredName("   ")).toEqual({ last_name: "", first_name: "", other_names: "" });
  });
});

describe("userDisplayName", () => {
  it("identifies an admin by the login they actually use", () => {
    expect(
      userDisplayName({ username: "localadmin", role: "admin", member_name: "Ada Obi" })
    ).toBe("localadmin");
  });

  it("identifies a member by their stored name in Last, First form", () => {
    // Printed names keep other names in full; the greeting is what abbreviates.
    expect(
      userDisplayName({ username: "MCT-0001", role: "member", member_name: "Okafor, Adaeze Ngozi" })
    ).toBe("Okafor, Adaeze Ngozi");
    expect(
      userDisplayName({ username: "MCT-0001", role: "member", member_name: "Adaeze Okafor" })
    ).toBe("Okafor, Adaeze");
  });

  it("falls back to the login when a member has no linked record", () => {
    expect(userDisplayName({ username: "MCT-0001", role: "member", member_name: null })).toBe(
      "MCT-0001"
    );
    expect(userDisplayName({ username: "localadmin" })).toBe("localadmin");
  });

  it("has nothing to show without a user", () => {
    expect(userDisplayName(null)).toBeNull();
    expect(userDisplayName(undefined)).toBeNull();
  });
});
