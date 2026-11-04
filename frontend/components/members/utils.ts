import { ApiError } from "@/lib/api";
import type { NokMemberOption } from "./types";

export function describeMemberOption(m: NokMemberOption): string {
  return `${m.psn} — ${m.name}`;
}

/** Appends the eligible-approvers list to a self-conflict error message,
 * when the backend included one (self_conflict.py / require_no_self_conflict),
 * so the admin sees who else can do this instead of just a dead-end
 * denial. Falls back to the plain message for any other kind of error. */
export function describeError(e: unknown): string {
  if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
    const detail = e.detail as { eligible_approvers?: { username: string }[]; no_eligible_approver_available?: boolean };
    if (detail.eligible_approvers) {
      if (detail.eligible_approvers.length > 0) {
        const names = detail.eligible_approvers.map((a) => a.username).join(", ");
        return `${e.message} Eligible approvers: ${names}.`;
      }
      if (detail.no_eligible_approver_available) {
        return `${e.message} No other eligible officer currently holds this permission.`;
      }
    }
  }
  return e instanceof Error ? e.message : String(e);
}
