import { useEffect, useRef } from "react";

import StatusMessage from "@/components/ui/StatusMessage";
import { INTEREST_MODE_LABELS } from "@/lib/loanMath";
import type { Member } from "@/lib/api";
import type { DashboardPageModel } from "../hooks/useDashboardPage";

import styles from "./ApplyForLoan.module.css";

const STEPS = ["Loan request", "Terms and payout", "Fee payment", "Review and submit"];

function money(value: number) {
  return `₦${value.toLocaleString("en-NG", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function ApplyForLoan({
  apply,
  member,
}: {
  apply: DashboardPageModel["apply"];
  member: Member | null;
}) {
  const { form, preview, selectedType, applyableTypes } = apply;
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (apply.showForm) headingRef.current?.focus();
  }, [apply.showForm, apply.step]);

  const toggleButton = (
    <button
      type="button"
      className={`btn ${apply.showForm ? "btn-secondary" : "btn-primary"}`}
      onClick={apply.toggle}
      aria-expanded={apply.showForm}
      aria-controls="loan-application-form"
      disabled={apply.submitting}
    >
      {apply.showForm ? "Cancel application" : "Apply for a loan"}
    </button>
  );

  if (!apply.showForm) {
    return <section className={styles.applySection}>{toggleButton}</section>;
  }

  const destination = form.use_default_account
    ? [member?.bank_name, member?.account_number].filter(Boolean).join(" · ") ||
      "Your account on file"
    : [form.alternate_bank_name, form.alternate_account_number].filter(Boolean).join(" · ");
  const monthlyPayment =
    preview.installment +
    (preview.interestInstallment > 0
      ? ` + ${money(preview.interestInstallment)} interest for the first ${preview.spreadMonths} months`
      : "");

  return (
    <section className={styles.applySection}>
      {toggleButton}

      <div className={styles.panel} id="loan-application-form">
          <div className={styles.header}>
            <div>
              <p className={styles.eyebrow}>Step {apply.step} of 4</p>
              <h3 ref={headingRef} tabIndex={-1} className={styles.title}>
                {STEPS[apply.step - 1]}
              </h3>
            </div>
            <span className={styles.feeBadge}>One loan fee: {money(preview.fee)}</span>
          </div>

          <ol className={styles.stepper} aria-label="Application progress">
            {STEPS.map((label, index) => {
              const step = index + 1;
              return (
                <li
                  key={label}
                  className={`${styles.step} ${step === apply.step ? styles.stepCurrent : ""} ${
                    step < apply.step ? styles.stepComplete : ""
                  }`}
                  aria-current={step === apply.step ? "step" : undefined}
                >
                  <span className={styles.stepNumber} aria-hidden="true">
                    {step < apply.step ? "✓" : step}
                  </span>
                  <span>{label}</span>
                </li>
              );
            })}
          </ol>

          <form className={styles.form} onSubmit={apply.submit} noValidate>
            {apply.error && <StatusMessage tone="error">{apply.error}</StatusMessage>}

            {apply.step === 1 && (
              <div className={styles.stepPanel} role="group" aria-label="Loan request">
                <div className={styles.fields}>
                  <label className={styles.field}>
                    Loan type
                    <select
                      required
                      value={form.loan_type_id}
                      onChange={(event) => apply.setField("loan_type_id", event.target.value)}
                      disabled={apply.submitting}
                    >
                      <option value="">Select loan type</option>
                      {applyableTypes.map((type) => (
                        <option key={type.id} value={type.id}>
                          {type.name} ({(parseFloat(type.interest_rate) * 100).toFixed(1)}%,{" "}
                          {type.tenure_months} months)
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className={styles.field}>
                    Amount requested
                    <input
                      required
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={form.requested_amount || ""}
                      onChange={(event) =>
                        apply.setField("requested_amount", parseFloat(event.target.value) || 0)
                      }
                      disabled={apply.submitting}
                    />
                  </label>

                  <label className={`${styles.field} ${styles.fieldFull}`}>
                    Requested tenure in months (optional)
                    <input
                      type="number"
                      min="1"
                      max={selectedType?.tenure_months}
                      step="1"
                      value={form.requested_tenure_months}
                      onChange={(event) =>
                        apply.setField(
                          "requested_tenure_months",
                          event.target.value ? parseInt(event.target.value) : ""
                        )
                      }
                      aria-describedby="tenure-help"
                      disabled={apply.submitting}
                    />
                    <span id="tenure-help" className={styles.help}>
                      Leave blank to use the {selectedType?.tenure_months ?? "loan type’s"} month
                      default. A shorter tenure may be requested.
                    </span>
                  </label>

                  <label className={`${styles.field} ${styles.fieldFull}`}>
                    Preferred disbursement date (optional)
                    <input
                      type="date"
                      value={form.preferred_disbursement_date}
                      onChange={(event) =>
                        apply.setField("preferred_disbursement_date", event.target.value)
                      }
                      disabled={apply.submitting}
                    />
                    <span className={styles.help}>
                      This is a preference only; the cooperative confirms actual timing.
                    </span>
                  </label>

                  <label className={`${styles.field} ${styles.fieldFull}`}>
                    Reason for the loan (optional)
                    <textarea
                      rows={3}
                      value={form.member_notes}
                      onChange={(event) => apply.setField("member_notes", event.target.value)}
                      disabled={apply.submitting}
                    />
                  </label>
                </div>
                {selectedType?.description && (
                  <p className={styles.description}>{selectedType.description}</p>
                )}
                {applyableTypes.length === 0 && (
                  <p className="notice">No loan types are currently open for application.</p>
                )}
              </div>
            )}

            {apply.step === 2 && (
              <div className={styles.stepPanel} role="group" aria-label="Terms and payout">
                <div className={styles.terms}>
                  <div className={styles.termsHeader}>
                    <strong>Estimated loan terms</strong>
                    <span>Final terms are set at approval and may differ.</span>
                  </div>
                  <dl className={styles.summary}>
                    <div>
                      <dt>Interest method</dt>
                      <dd>{INTEREST_MODE_LABELS[preview.mode]}</dd>
                    </div>
                    <div>
                      <dt>Estimated interest</dt>
                      <dd>{money(preview.interest)}</dd>
                    </div>
                    <div>
                      <dt>Estimated payout</dt>
                      <dd>{money(preview.netDisbursed)}</dd>
                    </div>
                    <div>
                      <dt>Total repayable</dt>
                      <dd>{money(preview.totalRepayable)}</dd>
                    </div>
                    <div>
                      <dt>Repayment period</dt>
                      <dd>{preview.tenure} months</dd>
                    </div>
                    <div>
                      <dt>Monthly payment</dt>
                      <dd>{monthlyPayment}</dd>
                    </div>
                  </dl>
                  <p className={styles.feeNote}>
                    The {money(preview.fee)} loan fee is paid separately and is not included in
                    these loan figures.
                  </p>
                </div>

                <div className={styles.fields}>
                  <label className={`${styles.checkbox} ${styles.fieldFull}`}>
                    <input
                      type="checkbox"
                      checked={form.use_default_account}
                      onChange={(event) => apply.setField("use_default_account", event.target.checked)}
                      disabled={apply.submitting}
                    />
                    Send funds to my account on file
                    {member?.account_number ? ` (${member.account_number})` : ""}
                  </label>
                  {!form.use_default_account && (
                    <>
                      <label className={styles.field}>
                        Bank name
                        <input
                          required
                          value={form.alternate_bank_name}
                          onChange={(event) =>
                            apply.setField("alternate_bank_name", event.target.value)
                          }
                          disabled={apply.submitting}
                        />
                      </label>
                      <label className={styles.field}>
                        Account name
                        <input
                          required
                          value={form.alternate_account_name}
                          onChange={(event) =>
                            apply.setField("alternate_account_name", event.target.value)
                          }
                          disabled={apply.submitting}
                        />
                      </label>
                      <label className={`${styles.field} ${styles.fieldFull}`}>
                        Account number
                        <input
                          required
                          inputMode="numeric"
                          value={form.alternate_account_number}
                          onChange={(event) =>
                            apply.setField("alternate_account_number", event.target.value)
                          }
                          disabled={apply.submitting}
                        />
                      </label>
                    </>
                  )}
                </div>
              </div>
            )}

            {apply.step === 3 && (
              <div className={styles.stepPanel} role="group" aria-label="Fee payment">
                <div className={styles.paymentCallout}>
                  <span>Loan fee due before review</span>
                  <strong>{money(preview.fee)}</strong>
                  <p>
                    Pay this single fee by bank transfer, then enter the transfer reference and
                    attach your receipt. It will not be charged again after disbursement.
                  </p>
                </div>
                <div className={styles.fields}>
                  <label className={`${styles.field} ${styles.fieldFull}`}>
                    Bank transfer reference
                    <input
                      required
                      value={form.payment_reference}
                      onChange={(event) => apply.setField("payment_reference", event.target.value)}
                      disabled={apply.submitting}
                    />
                  </label>
                  <label className={`${styles.field} ${styles.fieldFull}`}>
                    Payment receipt (photo or PDF)
                    <input
                      required
                      type="file"
                      accept="image/*,application/pdf"
                      onChange={(event) => apply.setReceiptFile(event.target.files?.[0] || null)}
                      disabled={apply.submitting}
                    />
                    {apply.receiptFile && (
                      <span className={styles.help}>Selected: {apply.receiptFile.name}</span>
                    )}
                  </label>
                </div>
                <p className={styles.description}>
                  The cooperative verifies your payment before the loan decision. The fee is not
                  refunded if you cancel or the application is not approved.
                </p>
              </div>
            )}

            {apply.step === 4 && (
              <div className={styles.stepPanel} role="group" aria-label="Review and submit">
                <div className={styles.reviewGrid}>
                  <section className={styles.reviewSection}>
                    <h5>Loan request</h5>
                    <dl className={styles.summary}>
                      <div>
                        <dt>Loan type</dt>
                        <dd>{selectedType?.name ?? "Not selected"}</dd>
                      </div>
                      <div>
                        <dt>Amount requested</dt>
                        <dd>{money(form.requested_amount)}</dd>
                      </div>
                      <div>
                        <dt>Tenure</dt>
                        <dd>{form.requested_tenure_months || preview.tenure} months</dd>
                      </div>
                      <div>
                        <dt>Preferred date</dt>
                        <dd>{form.preferred_disbursement_date || "No preference"}</dd>
                      </div>
                      {form.member_notes && (
                        <div>
                          <dt>Reason</dt>
                          <dd>{form.member_notes}</dd>
                        </div>
                      )}
                    </dl>
                  </section>

                  <section className={styles.reviewSection}>
                    <h5>Terms and payout</h5>
                    <dl className={styles.summary}>
                      <div>
                        <dt>Interest method</dt>
                        <dd>{INTEREST_MODE_LABELS[preview.mode]}</dd>
                      </div>
                      <div>
                        <dt>Estimated payout</dt>
                        <dd>{money(preview.netDisbursed)}</dd>
                      </div>
                      <div>
                        <dt>Total repayable</dt>
                        <dd>{money(preview.totalRepayable)}</dd>
                      </div>
                      <div>
                        <dt>Monthly payment</dt>
                        <dd>{monthlyPayment}</dd>
                      </div>
                      <div>
                        <dt>Payout account</dt>
                        <dd>{destination}</dd>
                      </div>
                    </dl>
                  </section>

                  <section className={`${styles.reviewSection} ${styles.reviewFull}`}>
                    <h5>Fee payment</h5>
                    <dl className={styles.summary}>
                      <div>
                        <dt>Fee recorded with this application</dt>
                        <dd>{money(preview.fee)}</dd>
                      </div>
                      <div>
                        <dt>Transfer reference</dt>
                        <dd>{form.payment_reference}</dd>
                      </div>
                      <div>
                        <dt>Receipt</dt>
                        <dd>{apply.receiptFile?.name}</dd>
                      </div>
                    </dl>
                  </section>
                </div>
                <p className="notice">
                  Submitting sends your request and payment proof for review. Approval and
                  disbursement are separate cooperative decisions.
                </p>
              </div>
            )}

            <div className={styles.actions}>
              {apply.step > 1 && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => apply.goToStep((apply.step - 1) as 1 | 2 | 3)}
                  disabled={apply.submitting}
                >
                  Back
                </button>
              )}
              <span className={styles.actionSpacer} />
              {apply.step < 4 ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => apply.goToStep((apply.step + 1) as 2 | 3 | 4)}
                  disabled={apply.submitting}
                >
                  Continue
                </button>
              ) : (
                <button type="submit" className="btn btn-primary" disabled={apply.submitting}>
                  {apply.submitting ? "Submitting…" : "Submit application"}
                </button>
              )}
            </div>
          </form>
        </div>
    </section>
  );
}
