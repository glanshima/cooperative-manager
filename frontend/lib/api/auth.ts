import { apiFetch, setToken, clearToken } from "./client";

export type UserRole = "admin" | "member";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: UserRole;
  must_change_password: boolean;
}

export type AccountStatus = "pending" | "active" | "suspended" | "deactivated";

export interface CurrentUser {
  id: string;
  username: string;
  role: UserRole;
  member_id?: string | null;
  // Present on GET /api/auth/me when the account is linked to a member record.
  member_name?: string | null;
  must_change_password: boolean;
  is_active: boolean;
  account_status: AccountStatus;
  is_super_admin: boolean;
  last_login_at?: string | null;
  created_at: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const result = await apiFetch<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: { username, password },
  });
  setToken(result.access_token);
  return result;
}

export function logout() {
  // Best-effort server-side session revocation -- fire and forget so the
  // UI doesn't hang on network issues during logout. Local token is
  // cleared either way.
  apiFetch("/api/auth/logout", { method: "POST" }).catch(() => {});
  clearToken();
}

export async function getMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/me");
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export async function createMemberLogin(memberId: string, temporaryPassword: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/create-member-login", {
    method: "POST",
    body: { member_id: memberId, temporary_password: temporaryPassword },
  });
}

export async function resetMemberPassword(memberId: string, temporaryPassword: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/reset-member-password", {
    method: "POST",
    body: { member_id: memberId, temporary_password: temporaryPassword },
  });
}

export async function forgotPassword(identifier: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/api/auth/forgot-password", {
    method: "POST",
    body: { identifier },
  });
}

export async function verifyResetToken(token: string): Promise<{ valid: boolean }> {
  return apiFetch<{ valid: boolean }>("/api/auth/verify-reset-token", {
    method: "POST",
    body: { token },
  });
}

export async function resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>("/api/auth/reset-password", {
    method: "POST",
    body: { token, new_password: newPassword },
  });
}
