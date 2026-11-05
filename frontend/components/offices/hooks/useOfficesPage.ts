import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { listOffices, createOffice, updateOffice, Office } from "@/lib/api";

export function useOfficesPage(authLoading: boolean, logout: () => void) {
  const [offices, setOffices] = useState<Office[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setOffices(await listOffices());
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
      await createOffice({ name, description: description || undefined });
      setName("");
      setDescription("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function toggleActive(office: Office) {
    setError(null);
    try {
      await updateOffice(office.id, { is_active: !office.is_active });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return {
    auth: { logout },
    feedback: { error },
    loading,
    table: { items: offices, onToggleActive: toggleActive },
    form: { name, description, setName, setDescription, submit: handleCreate },
  };
}

export type OfficesPageModel = ReturnType<typeof useOfficesPage>;
