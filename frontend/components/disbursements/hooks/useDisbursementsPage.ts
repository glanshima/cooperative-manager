import { useEffect, useState } from "react";

import {
  listLoanApplications,
  listLoanTypes,
  listLoans,
  disburseApplication,
  LoanApplication,
  LoanType,
  Loan,
} from "@/lib/api";

export function useDisbursementsPage(authLoading: boolean, logout: () => void) {
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [loanTypes, setLoanTypes] = useState<LoanType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [filterLoanTypeId, setFilterLoanTypeId] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");

  const [disbursing, setDisbursing] = useState<LoanApplication | null>(null);
  const [memberActiveLoans, setMemberActiveLoans] = useState<Loan[]>([]);
  const [selectedLoanIds, setSelectedLoanIds] = useState<string[]>([]);
  const [deductAll, setDeductAll] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [appsData, typesData] = await Promise.all([
        listLoanApplications({
          undisbursed_only: true,
          loan_type_id: filterLoanTypeId || undefined,
        }),
        listLoanTypes(),
      ]);
      setApplications(appsData);
      setLoanTypes(typesData);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, filterLoanTypeId]);

  const filteredApplications = applications.filter((a) => {
    if (!filterFrom && !filterTo) return true;
    const reviewed = a.reviewed_at ? a.reviewed_at.slice(0, 10) : null;
    if (!reviewed) return true;
    if (filterFrom && reviewed < filterFrom) return false;
    if (filterTo && reviewed > filterTo) return false;
    return true;
  });

  async function openDisburseDialog(app: LoanApplication) {
    setError(null);
    setDisbursing(app);
    setSelectedLoanIds([]);
    setDeductAll(false);
    try {
      const loans = await listLoans({ member_id: app.member_id, status: "active" });
      setMemberActiveLoans(loans);
    } catch (e: any) {
      setError(e.message);
    }
  }

  function toggleLoanSelected(id: string) {
    setSelectedLoanIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function toggleDeductAll(checked: boolean) {
    setDeductAll(checked);
    if (checked) setSelectedLoanIds([]);
  }

  async function confirmDisburse() {
    if (!disbursing) return;
    setError(null);
    setSuccess(null);
    try {
      await disburseApplication(
        disbursing.id,
        deductAll ? undefined : selectedLoanIds.length > 0 ? selectedLoanIds : undefined,
        deductAll
      );
      setSuccess(`Disbursed ${disbursing.member_name}'s loan.`);
      setDisbursing(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return {
    auth: { logout },
    feedback: { error, success },
    loading,
    filters: {
      loanTypeId: filterLoanTypeId,
      setLoanTypeId: setFilterLoanTypeId,
      from: filterFrom,
      setFrom: setFilterFrom,
      to: filterTo,
      setTo: setFilterTo,
      types: loanTypes,
    },
    table: { items: filteredApplications, onDisburse: openDisburseDialog },
    dialog: {
      application: disbursing,
      activeLoans: memberActiveLoans,
      selectedLoanIds,
      deductAll,
      onToggleLoan: toggleLoanSelected,
      onToggleDeductAll: toggleDeductAll,
      confirm: confirmDisburse,
      close: () => setDisbursing(null),
    },
  };
}

export type DisbursementsPageModel = ReturnType<typeof useDisbursementsPage>;
