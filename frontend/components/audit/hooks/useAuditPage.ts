import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { listAuditEvents, AuditEvent } from "@/lib/api";

export function useAuditPage(authLoading: boolean, logout: () => void) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const [entityType, setEntityType] = useState("");
  const [eventType, setEventType] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setEvents(
        await listAuditEvents({
          entity_type: entityType || undefined,
          event_type: eventType || undefined,
        })
      );
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

  function handleFilter(e: FormEvent) {
    e.preventDefault();
    refresh();
  }

  return {
    auth: { logout },
    feedback: { error },
    filters: {
      entityType,
      eventType,
      setEntityType,
      setEventType,
      submit: handleFilter,
    },
    table: { items: events, loading, onDetails: setSelected },
    detail: { event: selected, close: () => setSelected(null) },
  };
}

export type AuditPageModel = ReturnType<typeof useAuditPage>;
