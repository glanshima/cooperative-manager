/** The payroll month label ('YYYY-MM') the backend keys schedules on. */
export function currentMonth(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Accepts a month label or the ISO date the backend returns for one. */
export function monthLabel(value: string): string {
  const [year, month] = value.slice(0, 7).split("-").map(Number);
  if (!year || !month) return value;
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}