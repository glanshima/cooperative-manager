import { apiFetch } from "./client";
import type { AccountStatus, CurrentUser } from "./auth";

// ---------------------------------------------------------------------------
// Admin: Users, Offices, Roles, Permissions, Audit (Phase 1)
// ---------------------------------------------------------------------------

export async function listAdminUsers(): Promise<CurrentUser[]> {
  return apiFetch<CurrentUser[]>("/api/admin/users");
}

export async function createAdminUser(input: {
  username: string;
  password: string;
  account_status?: AccountStatus;
}): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/admin/users", { method: "POST", body: input });
}

export async function updateAdminUserStatus(
  userId: string,
  accountStatus: AccountStatus,
  reason?: string
): Promise<CurrentUser> {
  return apiFetch<CurrentUser>(`/api/admin/users/${userId}/status`, {
    method: "PATCH",
    body: { account_status: accountStatus, reason },
  });
}

export async function updateAdminUserMemberLink(
  userId: string,
  memberId: string | null,
  reason?: string
): Promise<CurrentUser> {
  return apiFetch<CurrentUser>(`/api/admin/users/${userId}/member-link`, {
    method: "PATCH",
    body: { member_id: memberId, reason: reason ?? null },
  });
}

export async function resetAdminUserPassword(
  userId: string,
  temporaryPassword: string
): Promise<CurrentUser> {
  return apiFetch<CurrentUser>(`/api/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: { temporary_password: temporaryPassword },
  });
}

export interface UserRoleAssignment {
  id: string;
  user_id: string;
  role_id: string;
  role_name: string;
  office_id?: string | null;
  office_name?: string | null;
  is_active: boolean;
  assigned_at: string;
  revoked_at?: string | null;
}

export async function listUserAssignments(userId: string): Promise<UserRoleAssignment[]> {
  return apiFetch<UserRoleAssignment[]>(`/api/admin/users/${userId}/assignments`);
}

export async function assignRole(
  userId: string,
  roleId: string,
  officeId?: string
): Promise<UserRoleAssignment> {
  return apiFetch<UserRoleAssignment>(`/api/admin/users/${userId}/assignments`, {
    method: "POST",
    body: { user_id: userId, role_id: roleId, office_id: officeId },
  });
}

export async function revokeRole(userId: string, assignmentId: string): Promise<void> {
  return apiFetch<void>(`/api/admin/users/${userId}/assignments/${assignmentId}`, {
    method: "DELETE",
  });
}

export interface Office {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
}

export async function listOffices(): Promise<Office[]> {
  return apiFetch<Office[]>("/api/offices");
}

export async function createOffice(input: { name: string; description?: string }): Promise<Office> {
  return apiFetch<Office>("/api/offices", { method: "POST", body: input });
}

export async function updateOffice(
  id: string,
  input: Partial<{ name: string; description: string; is_active: boolean }>
): Promise<Office> {
  return apiFetch<Office>(`/api/offices/${id}`, { method: "PUT", body: input });
}

export interface Permission {
  id: string;
  code: string;
  category: string;
  description: string;
}

export async function listPermissions(): Promise<Permission[]> {
  return apiFetch<Permission[]>("/api/permissions");
}

export interface Role {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  requires_member_link: boolean;
  created_at: string;
  permission_codes: string[];
}

export async function listRoles(): Promise<Role[]> {
  return apiFetch<Role[]>("/api/roles");
}

export async function createRole(input: {
  name: string;
  description?: string;
  requires_member_link?: boolean;
  permission_codes: string[];
}): Promise<Role> {
  return apiFetch<Role>("/api/roles", { method: "POST", body: input });
}

export async function updateRole(
  id: string,
  input: Partial<{
    name: string;
    description: string;
    is_active: boolean;
    requires_member_link: boolean;
    permission_codes: string[];
  }>
): Promise<Role> {
  return apiFetch<Role>(`/api/roles/${id}`, { method: "PUT", body: input });
}

export interface AuditEvent {
  id: string;
  actor_user_id?: string | null;
  actor_username?: string | null;
  actor_office_name?: string | null;
  actor_role_names?: string | null;
  event_type: string;
  entity_type?: string | null;
  entity_id?: string | null;
  action: string;
  previous_values?: Record<string, unknown> | null;
  new_values?: Record<string, unknown> | null;
  reason?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  timestamp: string;
}

export async function listAuditEvents(params?: {
  entity_type?: string;
  entity_id?: string;
  event_type?: string;
  actor_user_id?: string;
  start_time?: string;
  end_time?: string;
}): Promise<AuditEvent[]> {
  return apiFetch<AuditEvent[]>("/api/audit", { searchParams: params });
}
