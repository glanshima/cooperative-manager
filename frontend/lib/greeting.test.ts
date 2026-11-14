import { describe, expect, it } from "vitest";

import { timeOfDayGreeting } from "./greeting";

function at(hour: number, minute = 0): Date {
  return new Date(2026, 10, 14, hour, minute);
}

describe("timeOfDayGreeting", () => {
  it("greets the morning from 05:00 up to noon", () => {
    expect(timeOfDayGreeting(at(5))).toBe("Good morning");
    expect(timeOfDayGreeting(at(11, 59))).toBe("Good morning");
  });

  it("greets the afternoon from noon up to 17:00", () => {
    expect(timeOfDayGreeting(at(12))).toBe("Good afternoon");
    expect(timeOfDayGreeting(at(16, 59))).toBe("Good afternoon");
  });

  it("greets the evening from 17:00 through the night", () => {
    expect(timeOfDayGreeting(at(17))).toBe("Good evening");
    expect(timeOfDayGreeting(at(23, 59))).toBe("Good evening");
    expect(timeOfDayGreeting(at(0))).toBe("Good evening");
    expect(timeOfDayGreeting(at(4, 59))).toBe("Good evening");
  });
});
