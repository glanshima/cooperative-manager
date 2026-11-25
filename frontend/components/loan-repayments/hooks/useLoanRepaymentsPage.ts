import { useEffect, useState } from "react";

import {
  listAllRepayments,
  getRepayment,
  verifyRepayment,
  LoanRepayment,
  LoanRepaymentWithReceipt,
} from "@/lib/api";

export function useLoanRepaymentsPage(authLoading: boolean, logout: () => void) {
  const [repayments, setRepayments] = useState<LoanRepayment[]>([]);
  const [expanded, setExpanded] = useState<LoanRepaymentWithReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  // The dashboard's verification queue links here; "all" is the history.
  const [awaitingOnly, setAwaitingOnly] = useState(false);
  const [filterReady, setFilterReady] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setRepayments(await listAllRepayments(awaitingOnly ? "awaiting_verification" : undefined));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // The query string is only readable in the browser, so the first fetch
    // waits for it rather than loading the history first.
    const requested = new URLSearchParams(window.location.search).get("status");
    setAwaitingOnly(requested === "awaiting_verification");
    setFilterReady(true);
  }, []);

  useEffect(() => {
    if (!authLoading && filterReady) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, filterReady, awaitingOnly]);

  async function handleExpand(id: string) {
    setError(null);
    try {
      setExpanded(await getRepayment(id));
      setRejectionReason("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleVerify(approved: boolean) {
    if (!expanded) return;
    setError(null);
    try {
      await verifyRepayment(expanded.id, approved, approved ? undefined : rejectionReason);
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return {
    auth: { logout },
    feedback: { error },
    loading,
    filter: {
      awaitingOnly,
      clear: () => setAwaitingOnly(false),
    },
    table: { items: repayments, onReview: handleExpand },
    review: {
      repayment: expanded,
      rejectionReason,
      setRejectionReason,
      verify: handleVerify,
      close: () => setExpanded(null),
    },
  };
}

export type LoanRepaymentsPageModel = ReturnType<typeof useLoanRepaymentsPage>;
