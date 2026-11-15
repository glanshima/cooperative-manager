import Modal from "@/components/ui/Modal";
import { ConflictNotice } from "@/components/ui/ConflictMarker";
import { formatMoney } from "@/components/deductions/labels";
import type { Member } from "@/lib/api";
import { describeMemberOption } from "../utils";

function shown(value?: string | null): string {
  return value?.trim() ? value : "—";
}

function money(value?: string | null): string {
  return value ? `₦${formatMoney(value)}` : "—";
}

function nextOfKin(m: Member): string {
  if (m.next_of_kin_is_member && m.next_of_kin_member) {
    return `${describeMemberOption(m.next_of_kin_member)} (member)`;
  }
  if (m.next_of_kin_is_member === false) return shown(m.next_of_kin);
  return "—";
}

export default function MemberDetailsModal({
  member,
  onClose,
  onEdit,
  onDelete,
  onCreateLogin,
  onDeactivateLogin,
  onReactivateLogin,
  onWithdraw,
}: {
  member: Member;
  onClose: () => void;
  onEdit: (member: Member) => void;
  onDelete: (id: string) => void;
  onCreateLogin: (member: Member) => void;
  onDeactivateLogin: (member: Member) => void;
  onReactivateLogin: (member: Member) => void;
  onWithdraw: (member: Member) => void;
}) {
  return (
    <Modal
      title={member.name}
      onClose={onClose}
      closeLabel="Close member details"
      testId="member-details-backdrop"
      maxWidth={640}
    >
      <dl className="detail-grid">
        <div>
          <dt>PSN</dt>
          <dd>{shown(member.psn?.replace("MCT-", ""))}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            {member.status}
            {member.membership_exit_date && ` · exited ${member.membership_exit_date}`}
          </dd>
        </div>
        <div>
          <dt>Department</dt>
          <dd>{shown(member.department)}</dd>
        </div>
        <div>
          <dt>Gender</dt>
          <dd>{shown(member.gender)}</dd>
        </div>
        <div>
          <dt>Phone</dt>
          <dd>{shown(member.phone)}</dd>
        </div>
        <div className="detail-grid__full">
          <dt>Email</dt>
          <dd>{shown(member.email)}</dd>
        </div>
        <div>
          <dt>Bank</dt>
          <dd>{shown(member.bank_name)}</dd>
        </div>
        <div>
          <dt>Account number</dt>
          <dd>{shown(member.account_number)}</dd>
        </div>
        <div>
          <dt>Monthly contribution</dt>
          <dd>{money(member.monthly_contribution_amount)}</dd>
        </div>
        <div>
          <dt>Contribution effective from</dt>
          <dd>{shown(member.contribution_effective_from)}</dd>
        </div>
        <div>
          <dt>Loan restricted</dt>
          <dd>{member.loan_restricted ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt>Login</dt>
          <dd>{member.login_account_status ?? "No login"}</dd>
        </div>
        <div>
          <dt>Next of kin</dt>
          <dd>{nextOfKin(member)}</dd>
        </div>
        <div>
          <dt>Next of kin phone</dt>
          <dd>{shown(member.next_of_kin_phone)}</dd>
        </div>
        <div>
          <dt>Next of kin email</dt>
          <dd>{shown(member.next_of_kin_email)}</dd>
        </div>
        <div>
          <dt>Next of kin relationship</dt>
          <dd>{shown(member.next_of_kin_relationship)}</dd>
        </div>
        <div className="detail-grid__full">
          <dt>Next of kin address</dt>
          <dd>{shown(member.next_of_kin_address)}</dd>
        </div>
        {member.loan_restricted && (
          <div className="detail-grid__full">
            <dt>Restriction reason</dt>
            <dd>{shown(member.restriction_reason)}</dd>
          </div>
        )}
        {member.membership_exit_date && (
          <div className="detail-grid__full">
            <dt>Exit reason</dt>
            <dd>{shown(member.membership_exit_reason)}</dd>
          </div>
        )}
      </dl>

      {/* A conflicted member's record stays viewable -- this officer just
          isn't the one who may change it. */}
      {member.conflicted ? (
        <ConflictNotice entity="member" />
      ) : (
        <ul className="link-list">
          <li>
            <button type="button" className="link-button" onClick={() => onEdit(member)}>
              Edit member
            </button>
          </li>
          <li>
            <button type="button" className="link-button" onClick={() => onDelete(member.id)}>
              Delete member
            </button>
          </li>
          {!member.login_account_status && (
            <li>
              <button type="button" className="link-button" onClick={() => onCreateLogin(member)}>
                Create login
              </button>
            </li>
          )}
          {member.login_account_status === "active" && (
            <li>
              <button
                type="button"
                className="link-button"
                onClick={() => onDeactivateLogin(member)}
              >
                Deactivate login
              </button>
            </li>
          )}
          {(member.login_account_status === "deactivated" ||
            member.login_account_status === "suspended") && (
            <li>
              <button
                type="button"
                className="link-button"
                onClick={() => onReactivateLogin(member)}
              >
                Reactivate login
              </button>
            </li>
          )}
          {/* Once recorded the exit stands: it is a dated fact, not a
              status to toggle back. */}
          {!member.membership_exit_date && (
            <li>
              <button type="button" className="link-button" onClick={() => onWithdraw(member)}>
                Record exit
              </button>
            </li>
          )}
        </ul>
      )}
    </Modal>
  );
}
