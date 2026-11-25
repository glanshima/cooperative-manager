import { useEffect, useState } from "react";

import {
  listLoanApplications,
  getLoanApplication,
  verifyPayment,
  decideApplication,
  disburseApplication,
  LoanApplication,
  LoanApplicationWithReceipt,
} from "@/lib/api";

export type ApplicationQueueFilter = "review" | "payment" | null;

function readQueueFilter(): ApplicationQueueFilter {
  if (typeof window === "undefined") return null;
  const requested = new URLSearchParams(window.location.search).get("queue");
  return requested === "review" || requested === "payment" ? requested : null;
}

export function useLoanApplicationsPage(authLoading: boolean, logout: () => void) {
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [expanded, setExpanded] = useState<LoanApplicationWithReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The dashboard's queues link here with the queue they count, so the page
  // opens on exactly those rows instead of the whole application history.
  const [queueFilter, setQueueFilter] = useState<ApplicationQueueFilter>(null);
  const [filterReady, setFilterReady] = useState(false);

  const [approvedAmount, setApprovedAmount] = useState("");
  const [approvedTenureMonths, setApprovedTenureMonths] = useState("");
  const [tenureDecisionReason, setTenureDecisionReason] = useState("");
  const [adminNotes, setAdminNotes] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [canReapply, setCanReapply] = useState(true);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setApplications(
        await listLoanApplications(
          queueFilter === "review"
            ? { status: "pending", payment_status: "verified" }
            : queueFilter === "payment"
              ? { payment_status: "awaiting_verification" }
              : undefined
        )
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // The query string is only readable in the browser, so the first fetch
    // waits for it; otherwise the whole history would flash before the
    // filtered set replaces it.
    setQueueFilter(readQueueFilter());
    setFilterReady(true);
  }, []);

  useEffect(() => {
    if (!authLoading && filterReady) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, filterReady, queueFilter]);

  async function handleExpand(id: string) {
    setError(null);
    try {
      const full = await getLoanApplication(id);
      setExpanded(full);
      setApprovedAmount(full.requested_amount);
      setApprovedTenureMonths(
        full.requested_tenure_months ? String(full.requested_tenure_months) : ""
      );
      setTenureDecisionReason("");
      setAdminNotes("");
      setRejectionReason("");
      setCanReapply(true);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleVerifyPayment(approved: boolean) {
    if (!expanded) return;
    setError(null);
    try {
      await verifyPayment(expanded.id, approved, approved ? undefined : rejectionReason);
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDecide(approved: boolean) {
    if (!expanded) return;
    setError(null);
    try {
      await decideApplication(
        expanded.id,
        approved,
        approved ? parseFloat(approvedAmount) : undefined,
        approved ? parseInt(approvedTenureMonths) : undefined,
        tenureDecisionReason || undefined,
        adminNotes || undefined,
        canReapply
      );
      setExpanded(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDisburse(id: string) {
    if (!confirm("Disburse this loan now? This will move it to active and email the member.")) return;
    setError(null);
    try {
      await disburseApplication(id);
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
      current: queueFilter,
      clear: () => setQueueFilter(null),
    },
    table: {
      items: applications,
      onReview: handleExpand,
      onDisburse: handleDisburse,
    },
    review: {
      application: expanded,
      form: {
        approvedAmount,
        setApprovedAmount,
        approvedTenureMonths,
        setApprovedTenureMonths,
        tenureDecisionReason,
        setTenureDecisionReason,
        adminNotes,
        setAdminNotes,
        rejectionReason,
        setRejectionReason,
        canReapply,
        setCanReapply,
      },
      onVerifyPayment: handleVerifyPayment,
      onDecide: handleDecide,
      onDisburse: handleDisburse,
      close: () => setExpanded(null),
    },
  };
}

export type LoanApplicationsPageModel = ReturnType<typeof useLoanApplicationsPage>;
