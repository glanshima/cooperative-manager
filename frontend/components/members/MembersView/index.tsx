import StatusMessage from "@/components/ui/StatusMessage";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import type { MembersPageModel } from "../hooks/useMembersPage";
import ContributionReviewPanel from "../ContributionReviewPanel";
import MemberDetailsModal from "../MemberDetailsModal";
import MemberFilters from "../MemberFilters";
import MemberForm from "../MemberForm";
import MemberSearch from "../MemberSearch";
import MemberTable from "../MemberTable";

export default function MembersView({ model }: { model: MembersPageModel }) {
  const { table, filters, contributions, details } = model;

  return (
    <main className="page page--1100">
      <div className="page-header">
        <h1>Members</h1>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">Error: {model.feedback.error}</StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
      )}

      {/* Work that is waiting on this officer comes before the member
          records they come here to browse. */}
      {contributions.available && (
        <ContributionReviewPanel
          requests={contributions.requests}
          loading={contributions.loading}
          error={model.feedback.error}
          onRefresh={contributions.refresh}
          onApprove={contributions.approve}
          onReject={contributions.reject}
        />
      )}

      <section>
        <div className="page-header" style={{ marginBottom: 12 }}>
          <h2>Member records</h2>
          <button type="button" onClick={model.form.openCreate}>
            Add member
          </button>
        </div>

        {table.listError && (
          <StatusMessage tone="error">Error loading members: {table.listError}</StatusMessage>
        )}

        <MemberSearch {...model.search} />
        <MemberFilters {...filters} />

        <section style={{ marginBottom: 24, color: "#555", fontSize: 14 }}>
          {table.loading ? (
            <span>Loading…</span>
          ) : (
            <>
              <strong>
                Showing {table.members.length === 0 ? 0 : table.skip + 1}
                {table.members.length > 0 ? `–${table.skip + table.members.length}` : ""} of{" "}
                {table.total} member
                {table.total === 1 ? "" : "s"}
              </strong>
              {filters.descriptions.length > 0 && <span> ({filters.descriptions.join(", ")})</span>}
            </>
          )}
        </section>

        <MemberTable
          members={table.members}
          loading={table.loading}
          listError={table.listError}
          skip={table.skip}
          total={table.total}
          limit={table.limit}
          onPageChange={table.onPageChange}
          onOpenDetails={details.open}
        />
      </section>

      {model.form.isOpen && <MemberForm form={model.form} />}

      {details.member && (
        <MemberDetailsModal
          member={details.member}
          onClose={details.close}
          // Editing replaces the details view rather than stacking a second
          // dialog on top of it.
          onEdit={(m) => {
            details.close();
            table.onEdit(m);
          }}
          onDelete={table.onDelete}
          onCreateLogin={table.onCreateLogin}
          onDeactivateLogin={table.onDeactivateLogin}
          onReactivateLogin={table.onReactivateLogin}
          onWithdraw={table.onWithdraw}
        />
      )}

      {model.confirmation.current && (
        <ConfirmDialog
          title={model.confirmation.current.title}
          message={model.confirmation.current.message}
          confirmLabel={model.confirmation.current.confirmLabel}
          busy={model.confirmation.busy}
          error={model.confirmation.error}
          onConfirm={model.confirmation.confirm}
          onCancel={model.confirmation.cancel}
        />
      )}
    </main>
  );
}
