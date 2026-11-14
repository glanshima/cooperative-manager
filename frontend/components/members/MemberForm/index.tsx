import Modal from "@/components/ui/Modal";
import type { MemberStatus } from "@/lib/api";
import type { MembersPageModel } from "../hooks/useMembersPage";
import NextOfKinFields from "../NextOfKinFields";

export default function MemberForm({ form }: { form: MembersPageModel["form"] }) {
  return (
    <Modal
      title={form.editingId ? "Edit member" : "Add member"}
      onClose={form.close}
      busy={form.busy}
      testId="member-modal-backdrop"
      closeLabel="Close member form"
      hint="Closing this form discards anything you have not saved."
    >
      <form onSubmit={form.submit} className="form-grid">
        <input
          required
          aria-label="PSN"
          placeholder="PSN *"
          value={form.values.psn}
          disabled={!!form.editingId}
          onChange={(e) => form.setField("psn", e.target.value)}
        />
        <input
          required
          aria-label="Last name"
          placeholder="Last name *"
          value={form.values.last_name ?? ""}
          onChange={(e) => form.setField("last_name", e.target.value)}
        />
        <input
          required
          aria-label="First name"
          placeholder="First name *"
          value={form.values.first_name ?? ""}
          onChange={(e) => form.setField("first_name", e.target.value)}
        />
        <input
          aria-label="Other name(s)"
          placeholder="Other name(s)"
          value={form.values.other_names ?? ""}
          onChange={(e) => form.setField("other_names", e.target.value)}
        />
        <input
          placeholder="Bank name"
          value={form.values.bank_name}
          onChange={(e) => form.setField("bank_name", e.target.value)}
        />
        <input
          placeholder="Account number"
          value={form.values.account_number}
          onChange={(e) => form.setField("account_number", e.target.value)}
        />
        <input
          placeholder="Department"
          value={form.values.department}
          onChange={(e) => form.setField("department", e.target.value)}
        />
        <input
          placeholder="Phone"
          value={form.values.phone}
          onChange={(e) => form.setField("phone", e.target.value)}
        />
        <input
          placeholder="Email"
          value={form.values.email}
          onChange={(e) => form.setField("email", e.target.value)}
        />
        <div>
          <input
            type="number"
            step="0.01"
            min="5000"
            disabled={form.contributionLocked}
            placeholder="Monthly contribution amount (min ₦5,000)"
            value={form.values.monthly_contribution_amount ?? ""}
            onChange={(e) => form.setField("monthly_contribution_amount", e.target.value ? parseFloat(e.target.value) : null)}
            style={{ width: "100%" }}
            title={
              form.contributionLocked
                ? "Already on file — changes go through a contribution change request."
                : undefined
            }
          />
          {form.contributionLocked && (
            <p style={{ fontSize: 11, color: "#666", margin: "4px 0 0 0" }}>
              On file. Changes go through a contribution change request.
            </p>
          )}
        </div>

        <select
          value={form.values.status}
          onChange={(e) => form.setField("status", e.target.value as MemberStatus)}
        >
          <option value="financial">Financial</option>
          <option value="non_financial">Non-financial</option>
        </select>

        <NextOfKinFields form={form} />

        <label className="form-grid__full">
          <input
            type="checkbox"
            checked={form.values.loan_restricted}
            onChange={(e) => form.setField("loan_restricted", e.target.checked)}
          />{" "}
          Loan-restricted (flag this member as unable/limited to take new loans)
        </label>
        {form.values.loan_restricted && (
          <input
            className="form-grid__full"
            placeholder="Reason for restriction"
            value={form.values.restriction_reason}
            onChange={(e) => form.setField("restriction_reason", e.target.value)}
          />
        )}

        <div className="form-grid__full toolbar">
          <button type="submit" disabled={form.busy}>
            {form.editingId ? "Save changes" : "Add member"}
          </button>{" "}
          {form.editingId && (
            <button type="button" disabled={form.busy} onClick={form.close}>
              Cancel
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}
