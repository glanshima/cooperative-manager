import type { Member } from "@/lib/api";

export function describeMember(m: Member): string {
  return `${m.psn} — ${m.name}`;
}
