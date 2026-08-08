const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type MemberStatus = "financial" | "non_financial";

export interface Member {
  id: string;
  psn: string;
  name: string;
  bank_name?: string | null;
  account_number?: string | null;
  gender?: string | null;
  department?: string | null;
  phone?: string | null;
  email?: string | null;
  next_of_kin?: string | null;
  next_of_kin_phone?: string | null;
  status: MemberStatus;
  created_at: string;
  updated_at: string;
}

export interface MemberInput {
  psn: string;
  name: string;
  bank_name?: string;
  account_number?: string;
  gender?: string;
  department?: string;
  phone?: string;
  email?: string;
  next_of_kin?: string;
  next_of_kin_phone?: string;
  status: MemberStatus;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed with status ${res.status}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export async function listMembers(search?: string): Promise<Member[]> {
  const url = new URL(`${API_URL}/api/members`);
  if (search) url.searchParams.set("search", search);
  const res = await fetch(url.toString(), { cache: "no-store" });
  return handle<Member[]>(res);
}

export async function createMember(input: MemberInput): Promise<Member> {
  const res = await fetch(`${API_URL}/api/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Member>(res);
}

export async function updateMember(
  id: string,
  input: Partial<MemberInput>
): Promise<Member> {
  const res = await fetch(`${API_URL}/api/members/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Member>(res);
}

export async function deleteMember(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/members/${id}`, { method: "DELETE" });
  return handle<void>(res);
}
