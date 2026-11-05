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

export function useLoanApplicationsPage(authLoading: boolean, logout: () => void) {
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [expanded, setExpanded] = useState<LoanApplicationWithReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      setApplications(await listLoanApplications());
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
