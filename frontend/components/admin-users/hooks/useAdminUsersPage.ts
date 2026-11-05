import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  listAdminUsers,
  createAdminUser,
  updateAdminUserStatus,
  updateAdminUserMemberLink,
  resetAdminUserPassword,
  listUserAssignments,
  assignRole,
  revokeRole,
  listRoles,
  listOffices,
  listMembers,
  CurrentUser,
  UserRoleAssignment,
  Role,
  Office,
  Member,
  AccountStatus,
} from "@/lib/api";

import { describeMember } from "../utils";

export function useAdminUsersPage(authLoading: boolean, logout: () => void) {
  const [users, setUsers] = useState<CurrentUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [offices, setOffices] = useState<Office[]>([]);
  // Map of member.id -> Member, used only to display "PSN — Name" next to
  // an admin's member_id (a plain UUID on its own isn't useful to a human).
  // Built from the existing GET /api/members endpoint rather than adding a
  // new backend endpoint for this.
  const [memberDirectory, setMemberDirectory] = useState<Map<string, Member>>(new Map());

  const [loading, setLoading] = useState(true);

  // List-loading failures and individual-operation failures are two
  // SEPARATE states. Every operation clears BOTH actionError and success
  // at its own start (via beginAction), so a stale message from operation N
  // is never still showing once operation N+1 starts.
  const [listError, setListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [assignments, setAssignments] = useState<UserRoleAssignment[]>([]);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newUserMemberQuery, setNewUserMemberQuery] = useState("");
  const [newUserMemberResults, setNewUserMemberResults] = useState<Member[]>([]);
  const [newUserSelectedMember, setNewUserSelectedMember] = useState<Member | null>(null);

  // Which admin's member-link dialog is open -- link OR change, same dialog.
  const [linkDialogUserId, setLinkDialogUserId] = useState<string | null>(null);
  const [linkQuery, setLinkQuery] = useState("");
  const [linkResults, setLinkResults] = useState<Member[]>([]);
  const [linkSelectedMember, setLinkSelectedMember] = useState<Member | null>(null);

  const [resetPasswordUserId, setResetPasswordUserId] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState("");

  // Every mutating operation shares ONE sequence counter: only the result
  // of the MOST RECENTLY started operation is applied to actionError/
  // success, so a slow older failure can't clobber a newer success.
  const actionSeqRef = useRef(0);
  // Separate sequence counter for the list-loading refresh() itself, so an
  // old, slow reload can't overwrite a newer one's data either.
  const listSeqRef = useRef(0);

  function beginAction(): number {
    const seq = ++actionSeqRef.current;
    setActionError(null);
    setSuccess(null);
    return seq;
  }
  function isCurrentAction(seq: number): boolean {
    return seq === actionSeqRef.current;
  }

  async function refresh() {
    const mySeq = ++listSeqRef.current;
    setLoading(true);
    setListError(null);
    try {
      const [u, r, o, memberResult] = await Promise.all([
        listAdminUsers(),
        listRoles(),
        listOffices(),
        listMembers({ limit: 1000 }),
      ]);
      if (mySeq !== listSeqRef.current) return;
      setUsers(u);
      setRoles(r);
      setOffices(o);
      setMemberDirectory(new Map(memberResult.items.map((m) => [m.id, m])));
    } catch (e: any) {
      if (mySeq !== listSeqRef.current) return;
      setListError(e.message);
    } finally {
      if (mySeq === listSeqRef.current) setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  async function searchMembersFor(query: string, setResults: (m: Member[]) => void) {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    try {
      const result = await listMembers({ search: query, limit: 10 });
      setResults(result.items);
    } catch {
      // A failed search suggestion shouldn't blow away whatever the
      // top-level actionError is currently showing -- just show nothing.
      setResults([]);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const seq = beginAction();
    try {
      const user = await createAdminUser({ username: newUsername, password: newPassword });

      // Linking is a SEPARATE call to the SAME authoritative member-link
      // endpoint used everywhere else. If this second step fails, the admin
      // account was still created -- say so plainly rather than leaving an
      // ambiguous "did it work?" state.
      if (newUserSelectedMember) {
        try {
          await updateAdminUserMemberLink(user.id, newUserSelectedMember.id, "Linked at creation");
        } catch (linkErr: any) {
          if (!isCurrentAction(seq)) return;
          setActionError(
            `Admin "${user.username}" was created, but linking to ${describeMember(
              newUserSelectedMember
            )} failed: ${linkErr.message}. You can link them manually below.`
          );
          setNewUsername("");
          setNewPassword("");
          setNewUserSelectedMember(null);
          setNewUserMemberQuery("");
          setNewUserMemberResults([]);
          await refresh();
          return;
        }
      }

      if (!isCurrentAction(seq)) return;
      setSuccess(
        `Created admin "${user.username}"${
          newUserSelectedMember ? ` and linked to ${describeMember(newUserSelectedMember)}` : ""
        }.`
      );
      setNewUsername("");
      setNewPassword("");
      setNewUserSelectedMember(null);
      setNewUserMemberQuery("");
      setNewUserMemberResults([]);
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleStatusChange(user: CurrentUser, status: AccountStatus) {
    const reason = window.prompt(`Reason for setting ${user.username} to ${status}? (optional)`) || undefined;
    const seq = beginAction();
    try {
      await updateAdminUserStatus(user.id, status, reason);
      if (!isCurrentAction(seq)) return;
      setSuccess(`Updated ${user.username}'s status to ${status}.`);
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function toggleExpand(user: CurrentUser) {
    if (expandedUserId === user.id) {
      setExpandedUserId(null);
      return;
    }
    const seq = beginAction();
    setExpandedUserId(user.id);
    try {
      const result = await listUserAssignments(user.id);
      if (!isCurrentAction(seq)) return;
      setAssignments(result);
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleAssignRole(userId: string, roleId: string, officeId: string) {
    if (!roleId) return;
    const seq = beginAction();
    try {
      await assignRole(userId, roleId, officeId || undefined);
      const result = await listUserAssignments(userId);
      if (!isCurrentAction(seq)) return;
      setAssignments(result);
      setSuccess("Role assigned.");
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleRevoke(userId: string, assignmentId: string) {
    const seq = beginAction();
    try {
      await revokeRole(userId, assignmentId);
      const result = await listUserAssignments(userId);
      if (!isCurrentAction(seq)) return;
      setAssignments(result);
      setSuccess("Role revoked.");
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  async function handleAdminPasswordReset(userId: string) {
    if (!tempPassword) return;
    const seq = beginAction();
    try {
      await resetAdminUserPassword(userId, tempPassword);
      if (!isCurrentAction(seq)) return;
      setSuccess("Password reset successfully. The user must change it on next login.");
      setResetPasswordUserId(null);
      setTempPassword("");
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  function openLinkDialog(user: CurrentUser) {
    setLinkDialogUserId(user.id);
    setLinkQuery("");
    setLinkResults([]);
    setLinkSelectedMember(null);
  }

  function closeLinkDialog() {
    setLinkDialogUserId(null);
    setLinkQuery("");
    setLinkResults([]);
    setLinkSelectedMember(null);
  }

  async function confirmLink(user: CurrentUser) {
    if (!linkSelectedMember) return;
    const seq = beginAction();
    try {
      await updateAdminUserMemberLink(
        user.id,
        linkSelectedMember.id,
        `Linked via Admin Users UI to ${describeMember(linkSelectedMember)}`
      );
      if (!isCurrentAction(seq)) return;
      setSuccess(`Linked ${user.username} to ${describeMember(linkSelectedMember)}.`);
      closeLinkDialog();
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      // Deliberately does NOT close the dialog on failure -- the admin
      // should see the error next to the selection they just made.
      setActionError(e.message);
    }
  }

  async function handleUnlink(user: CurrentUser) {
    const currentMember = user.member_id ? memberDirectory.get(user.member_id) : undefined;
    const label = currentMember ? describeMember(currentMember) : "the linked member";
    if (!window.confirm(`Unlink ${user.username} from ${label}?`)) return;
    const seq = beginAction();
    try {
      await updateAdminUserMemberLink(user.id, null, "Unlinked via Admin Users UI");
      if (!isCurrentAction(seq)) return;
      setSuccess(`Unlinked ${user.username} from ${label}.`);
      await refresh();
    } catch (e: any) {
      if (!isCurrentAction(seq)) return;
      setActionError(e.message);
    }
  }

  function toggleResetPassword(userId: string) {
    setResetPasswordUserId((current) => (current === userId ? null : userId));
    setTempPassword("");
  }

  function cancelResetPassword() {
    setResetPasswordUserId(null);
    setTempPassword("");
  }

  return {
    auth: { logout },
    loading,
    feedback: {
      actionError,
      success,
      listError,
      dismissActionError: () => setActionError(null),
    },
    create: {
      username: newUsername,
      password: newPassword,
      setUsername: setNewUsername,
      setPassword: setNewPassword,
      submit: handleCreate,
      member: {
        query: newUserMemberQuery,
        results: newUserMemberResults,
        selected: newUserSelectedMember,
        setQuery: setNewUserMemberQuery,
        search: () => searchMembersFor(newUserMemberQuery, setNewUserMemberResults),
        select: setNewUserSelectedMember,
        clear: () => setNewUserSelectedMember(null),
      },
    },
    table: {
      users,
      roles,
      offices,
      memberDirectory,
      expandedUserId,
      assignments,
      link: {
        dialogUserId: linkDialogUserId,
        query: linkQuery,
        results: linkResults,
        selected: linkSelectedMember,
        setQuery: setLinkQuery,
        search: () => searchMembersFor(linkQuery, setLinkResults),
        select: setLinkSelectedMember,
        clear: () => setLinkSelectedMember(null),
        open: openLinkDialog,
        close: closeLinkDialog,
        confirm: confirmLink,
      },
      reset: {
        userId: resetPasswordUserId,
        tempPassword,
        toggle: toggleResetPassword,
        setTempPassword,
        confirm: handleAdminPasswordReset,
        cancel: cancelResetPassword,
      },
      onToggleExpand: toggleExpand,
      onStatusChange: handleStatusChange,
      onUnlink: handleUnlink,
      onRoleAssign: handleAssignRole,
      onRoleRevoke: handleRevoke,
    },
  };
}

export type AdminUsersPageModel = ReturnType<typeof useAdminUsersPage>;
