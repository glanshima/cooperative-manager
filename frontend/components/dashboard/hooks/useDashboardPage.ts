import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import {
  listLoanApplications,
  submitLoanApplication,
  listLoanTypes,
  listLoans,
  getMyMemberRecord,
  getSettings,
  fileToBase64,
  submitRepayment,
  cancelApplication,
  rescheduleApplication,
  reapplyLoanApplication,
  LoanApplication,
  LoanType,
  Loan,
  Member,
  Settings,
  CurrentUser,
} from "@/lib/api";

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
  const [settings, setSettings] = useState<Settings | null>(null);

  const [form, setForm] = useState<LoanApplicationFormValues>(EMPTY_APPLICATION_FORM);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [showApplyForm, setShowApplyForm] = useState(false);

  const [servicingLoanId, setServicingLoanId] = useState<string | null>(null);
  const [reapplyFromId, setReapplyFromId] = useState<string | null>(null);
  const [repayAmount, setRepayAmount] = useState(0);
  const [repayReference, setRepayReference] = useState("");
  const [repayReceiptFile, setRepayReceiptFile] = useState<File | null>(null);

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

      if (settingsData.loans_module_enabled) {
        const [appsData, loansData, typesData] = await Promise.all([
          listLoanApplications(),
          listLoans(),
          listLoanTypes(),
        ]);
        setApplications(appsData);
        setLoans(loansData);
        setLoanTypes(typesData);
      } else {
        setApplications([]);
        setLoans([]);
        setLoanTypes([]);
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

    try {
      const base64 = await fileToBase64(repayReceiptFile);
      await submitRepayment(servicingLoanId, {
        amount_claimed: repayAmount,
        payment_reference: repayReference,
        receipt_image_base64: base64,
        receipt_content_type: repayReceiptFile.type,
      });
      setSuccess("Repayment submitted for verification.");
      setServicingLoanId(null);
      setRepayAmount(0);
      setRepayReference("");
      setRepayReceiptFile(null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const applyableTypes = loanTypes.filter((t) => t.is_active && t.open_for_application);
  const selectedType = applyableTypes.find((t) => t.id === form.loan_type_id);

  const previewTenure = form.requested_tenure_months || selectedType?.tenure_months || 0;
  const previewInterest =
    selectedType && form.requested_amount
      ? form.requested_amount * parseFloat(selectedType.interest_rate)
      : 0;
  const previewFlatCharge = selectedType ? parseFloat(selectedType.flat_charge) : 0;
  const previewNetDisbursed = form.requested_amount - previewInterest;
  const previewTotalRepayable = form.requested_amount + previewFlatCharge;
  const previewInstallment = previewTenure > 0 ? previewTotalRepayable / previewTenure : 0;

  return {
    auth: { logout },
    loading,
    member,
    settings,
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
        interest: previewInterest,
        flatCharge: previewFlatCharge,
        netDisbursed: previewNetDisbursed,
        totalRepayable: previewTotalRepayable,
        installment: previewInstallment,
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
      repayReference,
      setRepayReference,
      repayReceiptFile,
      setRepayReceiptFile,
      startRepayment: handleStartRepayment,
      submitRepayment: handleSubmitRepayment,
      cancelRepayment: () => setServicingLoanId(null),
    },
  };
}

export type DashboardPageModel = ReturnType<typeof useDashboardPage>;
