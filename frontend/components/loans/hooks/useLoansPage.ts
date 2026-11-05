import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import {
  Loan,
  LoanInput,
  LoanType,
  LoanTypeCreateInput,
  LoanTypeRateVersion,
  listLoans,
  createLoan,
  updateLoan,
  deleteLoan,
  listLoanTypes,
  createLoanType,
  updateLoanType,
  listRateVersions,
  createRateVersion,
  listMembers,
  Member,
} from "@/lib/api";

export type RateVersionForm = {
  interest_rate: number;
  tenure_months: number;
  flat_charge: number;
  effective_from: string;
};

const today = () => new Date().toISOString().slice(0, 10);

export const EMPTY_LOAN_FORM: LoanInput = {
  member_id: "",
  loan_type_id: "",
  principal: 0,
  disbursement_date: today(),
  notes: "",
};

export const EMPTY_TYPE_FORM: LoanTypeCreateInput = {
  name: "",
  description: "",
  interest_rate: 0.15,
  tenure_months: 12,
  flat_charge: 0,
  is_active: true,
  open_for_application: false,
  effective_from: today(),
};

export function useLoansPage(authLoading: boolean, logout: () => void) {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loanTypes, setLoanTypes] = useState<LoanType[]>([]);
  const [members, setMembers] = useState<Member[]>([]);

  const [loanForm, setLoanForm] = useState<LoanInput>(EMPTY_LOAN_FORM);
  const [typeForm, setTypeForm] = useState<LoanTypeCreateInput>(EMPTY_TYPE_FORM);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTypeManager, setShowTypeManager] = useState(false);

  const [rateHistoryFor, setRateHistoryFor] = useState<LoanType | null>(null);
  const [rateHistory, setRateHistory] = useState<LoanTypeRateVersion[]>([]);
  const [newVersion, setNewVersion] = useState<RateVersionForm>({
    interest_rate: 0.15,
    tenure_months: 12,
    flat_charge: 0,
    effective_from: today(),
  });

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [loansData, typesData] = await Promise.all([listLoans(), listLoanTypes()]);
      setLoans(loansData);
      setLoanTypes(typesData);
      // The member picker needs the directory, but member management may be
      // disabled on its own. Treat that lookup as best-effort so the rest of
      // the Loans page still works.
      try {
        const membersData = await listMembers({ limit: 1000 });
        setMembers(membersData.items);
      } catch {
        setMembers([]);
      }
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

  function setLoanField<K extends keyof LoanInput>(key: K, value: LoanInput[K]) {
    setLoanForm((current) => ({ ...current, [key]: value }));
  }

  function setTypeField<K extends keyof LoanTypeCreateInput>(key: K, value: LoanTypeCreateInput[K]) {
    setTypeForm((current) => ({ ...current, [key]: value }));
  }

  function setVersionField<K extends keyof RateVersionForm>(key: K, value: RateVersionForm[K]) {
    setNewVersion((current) => ({ ...current, [key]: value }));
  }

  async function handleDisburse(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createLoan(loanForm);
      setLoanForm(EMPTY_LOAN_FORM);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleCreateType(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createLoanType(typeForm);
      setTypeForm(EMPTY_TYPE_FORM);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleToggleTypeActive(type: LoanType) {
    try {
      await updateLoanType(type.id, { is_active: !type.is_active });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleToggleOpenForApplication(type: LoanType) {
    try {
      await updateLoanType(type.id, { open_for_application: !type.open_for_application });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleShowRateHistory(type: LoanType) {
    setError(null);
    try {
      const versions = await listRateVersions(type.id);
      setRateHistoryFor(type);
      setRateHistory(versions);
      setNewVersion({
        interest_rate: parseFloat(type.interest_rate),
        tenure_months: type.tenure_months,
        flat_charge: parseFloat(type.flat_charge),
        effective_from: today(),
      });
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleCreateVersion(e: FormEvent) {
    e.preventDefault();
    if (!rateHistoryFor) return;
    setError(null);
    try {
      await createRateVersion(rateHistoryFor.id, newVersion);
      await handleShowRateHistory(rateHistoryFor);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleMarkRepaid(loan: Loan) {
    const amount = prompt(`Record a repayment for ${loan.member_name} (balance: ${loan.balance})`);
    if (!amount) return;
    const parsed = parseFloat(amount);
    if (isNaN(parsed)) return;
    try {
      const newAmountRepaid = parseFloat(loan.amount_repaid) + parsed;
      await updateLoan(loan.id, { amount_repaid: newAmountRepaid });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this loan record?")) return;
    try {
      await deleteLoan(id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const selectedType = loanTypes.find((t) => t.id === loanForm.loan_type_id);
  const previewInterest =
    selectedType && loanForm.principal
      ? loanForm.principal * parseFloat(selectedType.interest_rate)
      : 0;
  const previewFlatCharge = selectedType ? parseFloat(selectedType.flat_charge) : 0;
  const previewTotal = loanForm.principal + previewInterest + previewFlatCharge;
  const previewInstallment = selectedType ? previewTotal / selectedType.tenure_months : 0;

  return {
    auth: { logout },
    feedback: { error },
    loading,
    types: {
      items: loanTypes,
      showManager: showTypeManager,
      toggleManager: () => setShowTypeManager((current) => !current),
      form: typeForm,
      setField: setTypeField,
      submit: handleCreateType,
      onToggleActive: handleToggleTypeActive,
      onToggleOpenForApplication: handleToggleOpenForApplication,
      historyFor: rateHistoryFor,
      history: rateHistory,
      showHistory: handleShowRateHistory,
      closeHistory: () => setRateHistoryFor(null),
      newVersion,
      setVersionField,
      submitVersion: handleCreateVersion,
    },
    disburse: {
      form: loanForm,
      setField: setLoanField,
      members,
      activeTypes: loanTypes.filter((t) => t.is_active),
      selectedType,
      preview: {
        interest: previewInterest,
        flatCharge: previewFlatCharge,
        total: previewTotal,
        installment: previewInstallment,
      },
      submit: handleDisburse,
    },
    table: {
      items: loans,
      loading,
      onRecordRepayment: handleMarkRepaid,
      onDelete: handleDelete,
    },
  };
}

export type LoansPageModel = ReturnType<typeof useLoansPage>;
