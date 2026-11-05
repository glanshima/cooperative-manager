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

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setRepayments(await listAllRepayments());
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
