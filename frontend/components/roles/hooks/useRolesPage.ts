import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { listRoles, createRole, updateRole, listPermissions, Role, Permission } from "@/lib/api";

export function useRolesPage(authLoading: boolean, logout: () => void) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [editedCodes, setEditedCodes] = useState<Set<string>>(new Set());
  const [editedRequiresMemberLink, setEditedRequiresMemberLink] = useState(false);

  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newRequiresMemberLink, setNewRequiresMemberLink] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [r, p] = await Promise.all([listRoles(), listPermissions()]);
      setRoles(r);
      setPermissions(p);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createRole({
        name: newName,
        description: newDescription || undefined,
        requires_member_link: newRequiresMemberLink,
        permission_codes: [],
      });
      setNewName("");
      setNewDescription("");
      setNewRequiresMemberLink(false);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function startEdit(role: Role) {
    setEditingRoleId(role.id);
    setEditedCodes(new Set(role.permission_codes));
    setEditedRequiresMemberLink(role.requires_member_link);
  }

  function toggleCode(code: string) {
    setEditedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function saveEdit(role: Role) {
    setError(null);
    try {
      await updateRole(role.id, {
        permission_codes: Array.from(editedCodes),
        requires_member_link: editedRequiresMemberLink,
      });
      setEditingRoleId(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const categories = Array.from(new Set(permissions.map((p) => p.category)));

  return {
    auth: { logout },
    feedback: { error },
    loading,
    create: {
      name: newName,
      description: newDescription,
      requiresMemberLink: newRequiresMemberLink,
      setName: setNewName,
      setDescription: setNewDescription,
      setRequiresMemberLink: setNewRequiresMemberLink,
      submit: handleCreate,
    },
    list: { items: roles, permissions, categories },
    edit: {
      roleId: editingRoleId,
      codes: editedCodes,
      requiresMemberLink: editedRequiresMemberLink,
      start: startEdit,
      toggleCode,
      setRequiresMemberLink: setEditedRequiresMemberLink,
      save: saveEdit,
      cancel: () => setEditingRoleId(null),
    },
  };
}

export type RolesPageModel = ReturnType<typeof useRolesPage>;
