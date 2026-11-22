import { useEffect, useState } from "react";

import {
  LoanFeePaymentWithDetails,
  LoanFeePaymentWithReceipt,
  getFeePaymentReceipt,
  listAllFeePayments,
  verifyFeePayment,
} from "@/lib/api";

export type FeeQueueScope = "queue" | "all";

const FEEDBACK_TIMEOUT_MS = 6000;

// The queue is what needs an officer now; "all" is the history behind it.
export function useLoanFeesPage(authLoading: boolean, logout: () => void) {
  const [scope, setScope] = useState<FeeQueueScope>("queue");
  const [payments, setPayments] = useState<LoanFeePaymentWithDetails[]>([]);
  const [expanded, setExpanded] = useState<LoanFeePaymentWithReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");

  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), FEEDBACK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [error]);

  useEffect(() => {
    if (!success) return;
    const timer = setTimeout(() => setSuccess(null), FEEDBACK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [success]);

  async function refresh(currentScope: FeeQueueScope = scope) {
    setLoading(true);
    setError(null);
    try {
      setPayments(
        await listAllFeePayments(
          currentScope === "queue" ? "awaiting_verification" : undefined
        )
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh(scope);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, scope]);

  async function handleReview(id: string) {
    setError(null);
    try {
      setExpanded(await getFeePaymentReceipt(id));
      setRejectionReason("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleVerify(approved: boolean) {
    if (!expanded) return;
    setError(null);
    setSuccess(null);
    if (!approved && !rejectionReason.trim()) {
      setError("Please give the member a reason for the rejection.");
      return;
    }
    try {
      await verifyFeePayment(expanded.id, approved, approved ? undefined : rejectionReason.trim());
      setSuccess(approved ? "Fee payment verified." : "Fee payment rejected.");
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return {
    auth: { logout },
    feedback: {
      error,
      success,
      dismissError: () => setError(null),
      dismissSuccess: () => setSuccess(null),
    },
    scope,
    setScope,
    loading,
    total: payments.length,
    table: { items: payments, onReview: handleReview },
    review: {
      payment: expanded,
      rejectionReason,
      setRejectionReason,
      verify: handleVerify,
      close: () => setExpanded(null),
    },
  };
}

export type LoanFeesPageModel = ReturnType<typeof useLoanFeesPage>;
