import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import {
  listLoanApplications,
  submitLoanApplication,
  listLoanTypes,
  listLoans,
  listRepaymentsForLoan,
  getMemberLoanBalance,
  getMyMemberRecord,
  getMySavings,
  getMyDeductions,
  getNotifications,
  getSettings,
  fileToBase64,
  submitRepayment,
  submitFeePayment,
  cancelApplication,
  rescheduleApplication,
  reapplyLoanApplication,
  LoanApplication,
  LoanType,
  Loan,
  LoanRepayment,
  Member,
  MemberDeductions,
  MemberLoanBalance,
  MemberSavings,
  NotificationPage,
  Settings,
  CurrentUser,
} from "@/lib/api";
import { currentMonth, monthLabel } from "@/lib/month";
import { computeLoanPreview, resolveTypeInterestTerms } from "@/lib/loanMath";

export type LoanApplicationFormValues = {
  loan_type_id: string;
  requested_amount: number;
  requested_tenure_months: number | "";
  preferred_disbursement_date: string;
  use_default_account: boolean;
  alternate_bank_name: string;
  alternate_account_name: string;
  alternate_account_number: string;
  member_notes: string;
  payment_reference: string;
};

/** One row of the dashboard's recent-activity list, built only from
 *  authoritative records: a loan's own disbursement, an application's own
 *  request, a repayment's own claim. Never a running balance -- the member
 *  side has no ledger series to derive one from. */
export type DashboardActivityItem = {
  id: string;
  date: string;
  title: string;
  detail: string | null;
  amount: string;
  direction: "received" | "paid" | "requested";
  status: string | null;
};

export const EMPTY_APPLICATION_FORM: LoanApplicationFormValues = {
  loan_type_id: "",
  requested_amount: 0,
  requested_tenure_months: "",
  preferred_disbursement_date: "",
  use_default_account: true,
  alternate_bank_name: "",
  alternate_account_name: "",
  alternate_account_number: "",
  member_notes: "",
  payment_reference: "",
};

export function useDashboardPage(authLoading: boolean, user: CurrentUser | null, logout: () => void) {
  const [member, setMember] = useState<Member | null>(null);
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [loans, setLoans] = useState<Loan[]>([]);
  const [loanTypes, setLoanTypes] = useState<LoanType[]>([]);
  const [repayments, setRepayments] = useState<LoanRepayment[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);

  const [savings, setSavings] = useState<MemberSavings | null>(null);
  const [deductions, setDeductions] = useState<MemberDeductions | null>(null);
  const [loanBalance, setLoanBalance] = useState<MemberLoanBalance | null>(null);
  const [notifications, setNotifications] = useState<NotificationPage | null>(null);

  const [form, setForm] = useState<LoanApplicationFormValues>(EMPTY_APPLICATION_FORM);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [showApplyForm, setShowApplyForm] = useState(false);

  const [servicingLoanId, setServicingLoanId] = useState<string | null>(null);
  const [reapplyFromId, setReapplyFromId] = useState<string | null>(null);
  const [repayAmount, setRepayAmount] = useState(0);
  const [repayMonth, setRepayMonth] = useState(currentMonth());
  const [repayReference, setRepayReference] = useState("");
  const [repayReceiptFile, setRepayReceiptFile] = useState<File | null>(null);

  const [feePayingLoanId, setFeePayingLoanId] = useState<string | null>(null);
  const [feeReference, setFeeReference] = useState("");
  const [feeReceiptFile, setFeeReceiptFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [memberData, settingsData] = await Promise.all([
        getMyMemberRecord(),
        getSettings(),
      ]);
      setMember(memberData);
      setSettings(settingsData);

      const loansEnabledNow = Boolean(settingsData.loans_module_enabled);
      const deductionsEnabledNow = Boolean(settingsData.deductions_module_enabled);

      // Each dashboard figure is its own read: a failed savings lookup must
      // not blank the loan card, and vice versa. Null renders as an
      // unavailable state, never as zero.
      setSavings(await getMySavings().catch(() => null));
      setNotifications(await getNotifications({ limit: 3 }).catch(() => null));
      setDeductions(
        deductionsEnabledNow ? await getMyDeductions(currentMonth()).catch(() => null) : null
      );
      setLoanBalance(
        loansEnabledNow ? await getMemberLoanBalance(memberData.id).catch(() => null) : null
      );

      if (loansEnabledNow) {
        const [appsData, loansData, typesData] = await Promise.all([
          listLoanApplications(),
          listLoans(),
          listLoanTypes(),
        ]);
        setApplications(appsData);
        setLoans(loansData);
        setLoanTypes(typesData);
        const repaymentLists = await Promise.all(
          loansData.map((loan) => listRepaymentsForLoan(loan.id).catch(() => []))
        );
        setRepayments(repaymentLists.flat());
      } else {
        setApplications([]);
        setLoans([]);
        setLoanTypes([]);
        setRepayments([]);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && user) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  function setFormField<K extends keyof LoanApplicationFormValues>(
    key: K,
    value: LoanApplicationFormValues[K]
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmitApplication(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!receiptFile) {
      setError("Please attach your payment receipt.");
      return;
    }
    if (
      !form.use_default_account &&
      (!form.alternate_bank_name || !form.alternate_account_name || !form.alternate_account_number)
    ) {
      setError("Please provide the bank name, account name, and account number, or use your default account.");
      return;
    }

    try {
      const base64 = await fileToBase64(receiptFile);
      const commonFields = {
        requested_amount: form.requested_amount,
        requested_tenure_months: form.requested_tenure_months || undefined,
        preferred_disbursement_date: form.preferred_disbursement_date || undefined,
        use_default_account: form.use_default_account,
        alternate_bank_name: form.use_default_account ? undefined : form.alternate_bank_name,
        alternate_account_name: form.use_default_account ? undefined : form.alternate_account_name,
        alternate_account_number: form.use_default_account
          ? undefined
          : form.alternate_account_number,
        member_notes: form.member_notes,
        payment_reference: form.payment_reference,
        receipt_image_base64: base64,
        receipt_content_type: receiptFile.type,
      };

      if (reapplyFromId) {
        await reapplyLoanApplication(reapplyFromId, commonFields);
        setSuccess("Reapplication submitted. It will be reviewed once your payment is verified.");
      } else {
        await submitLoanApplication({ loan_type_id: form.loan_type_id, ...commonFields });
        setSuccess("Application submitted. It will be reviewed once your payment is verified.");
      }
      setForm(EMPTY_APPLICATION_FORM);
      setReceiptFile(null);
      setShowApplyForm(false);
      setReapplyFromId(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function handleStartReapply(app: LoanApplication) {
    setReapplyFromId(app.id);
    setForm({
      ...EMPTY_APPLICATION_FORM,
      loan_type_id: app.loan_type_id,
      requested_amount: parseFloat(app.requested_amount),
      requested_tenure_months: app.requested_tenure_months || "",
    });
    setShowApplyForm(true);
  }

  async function handleCancel(id: string) {
    if (
      !confirm(
        "Cancel this application? Your loan-form fee will NOT be refunded. " +
          "If you just want a different disbursement date, use Reschedule instead."
      )
    )
      return;
    setError(null);
    try {
      await cancelApplication(id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleReschedule(id: string) {
    const newDate = prompt("Enter your new preferred disbursement date (YYYY-MM-DD):");
    if (!newDate) return;
    setError(null);
    try {
      await rescheduleApplication(id, newDate);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function handleStartRepayment(loan: Loan) {
    setServicingLoanId(loan.id);
    setRepayAmount(parseFloat(loan.monthly_installment));
    setRepayMonth(currentMonth());
  }

  async function handleSubmitRepayment(e: FormEvent) {
    e.preventDefault();
    if (!servicingLoanId) return;
    setError(null);
    setSuccess(null);

    if (!repayReceiptFile) {
      setError("Please attach your payment receipt.");
      return;
    }
    if (!repayMonth) {
      setError("Choose the month this payment covers.");
      return;
    }

    try {
      const base64 = await fileToBase64(repayReceiptFile);
      await submitRepayment(servicingLoanId, {
        amount_claimed: repayAmount,
        payment_month: repayMonth,
        payment_reference: repayReference,
        receipt_image_base64: base64,
        receipt_content_type: repayReceiptFile.type,
      });
      setSuccess("Repayment submitted for verification.");
      setServicingLoanId(null);
      setRepayAmount(0);
      setRepayMonth(currentMonth());
      setRepayReference("");
      setRepayReceiptFile(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  function handleStartFeePayment(loan: Loan) {
    setFeePayingLoanId(loan.id);
    setFeeReference("");
    setFeeReceiptFile(null);
  }

  async function handleSubmitFeePayment(e: FormEvent) {
    e.preventDefault();
    if (!feePayingLoanId) return;
    setError(null);
    setSuccess(null);
    if (!feeReceiptFile) {
      setError("Please attach your payment receipt.");
      return;
    }
    try {
      const base64 = await fileToBase64(feeReceiptFile);
      await submitFeePayment(feePayingLoanId, {
        payment_reference: feeReference,
        receipt_image_base64: base64,
        receipt_content_type: feeReceiptFile.type,
      });
      setSuccess("Fee payment submitted for verification.");
      setFeePayingLoanId(null);
      setFeeReference("");
      setFeeReceiptFile(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const applyableTypes = loanTypes.filter((t) => t.is_active && t.open_for_application);
  const selectedType = applyableTypes.find((t) => t.id === form.loan_type_id);

  const previewTenure = form.requested_tenure_months || selectedType?.tenure_months || 0;
  const typeTerms = resolveTypeInterestTerms(
    selectedType,
    settings?.loan_interest_mode,
    settings?.loan_interest_spread_months
  );
  const preview = computeLoanPreview(
    form.requested_amount,
    selectedType ? parseFloat(selectedType.interest_rate) : 0,
    previewTenure,
    typeTerms.mode,
    typeTerms.spreadMonths,
    selectedType ? parseFloat(selectedType.flat_charge) : 0
  );

  const activity: DashboardActivityItem[] = [
    ...applications.map((app) => ({
      id: `application-${app.id}`,
      date: app.created_at,
      title: "Loan application",
      detail: app.requested_tenure_months ? `${app.requested_tenure_months} months` : null,
      amount: app.requested_amount,
      direction: "requested" as const,
      status: app.status,
    })),
    ...loans.map((loan) => ({
      id: `loan-${loan.id}`,
      date: loan.disbursement_date,
      title: "Loan disbursed",
      detail: loan.loan_type_name ?? null,
      amount: loan.net_disbursed,
      direction: "received" as const,
      status: null,
    })),
    ...repayments.map((repayment) => ({
      id: `repayment-${repayment.id}`,
      date: repayment.created_at,
      title: "Loan repayment",
      detail: repayment.payment_month ? monthLabel(repayment.payment_month) : null,
      amount: repayment.amount_claimed,
      direction: "paid" as const,
      status: repayment.status,
    })),
  ]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 6);

  return {
    auth: { user, logout },
    loading,
    member,
    settings,
    deductionsEnabled: settings ? settings.deductions_module_enabled : false,
    summary: { savings, deductions, loanBalance, notifications, activity },
    loansEnabled: settings ? settings.loans_module_enabled : true,
    feedback: { error, success },
    apply: {
      showForm: showApplyForm,
      toggle: () => setShowApplyForm((current) => !current),
      form,
      setField: setFormField,
      receiptFile,
      setReceiptFile,
      submit: handleSubmitApplication,
      applyableTypes,
      selectedType,
      preview: {
        tenure: previewTenure,
        mode: typeTerms.mode,
        spreadMonths: typeTerms.spreadMonths,
        interest: preview.interest,
        flatCharge: preview.fee,
        netDisbursed: preview.netDisbursed,
        totalRepayable: preview.totalRepayable,
        installment: preview.installment,
        interestInstallment: preview.interestInstallment,
      },
    },
    applications: {
      items: applications,
      onReschedule: handleReschedule,
      onCancel: handleCancel,
      onStartReapply: handleStartReapply,
    },
    loans: {
      items: loans,
      servicingLoanId,
      repayAmount,
      setRepayAmount,
      repayMonth,
      setRepayMonth,
      repayReference,
      setRepayReference,
      repayReceiptFile,
      setRepayReceiptFile,
      startRepayment: handleStartRepayment,
      submitRepayment: handleSubmitRepayment,
      cancelRepayment: () => setServicingLoanId(null),
      feePayingLoanId,
      feeReference,
      setFeeReference,
      feeReceiptFile,
      setFeeReceiptFile,
      startFeePayment: handleStartFeePayment,
      submitFeePayment: handleSubmitFeePayment,
      cancelFeePayment: () => setFeePayingLoanId(null),
    },
  };
}

export type DashboardPageModel = ReturnType<typeof useDashboardPage>;
