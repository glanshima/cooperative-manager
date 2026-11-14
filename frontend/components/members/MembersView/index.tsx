import StatusMessage from "@/components/ui/StatusMessage";
import LogoutControl from "@/components/ui/LogoutControl";
import type { MembersPageModel } from "../hooks/useMembersPage";
import MemberFilters from "../MemberFilters";
import MemberForm from "../MemberForm";
import MemberSearch from "../MemberSearch";
import MemberTable from "../MemberTable";
import ContributionReviewPanel from "../ContributionReviewPanel";

export default function MembersView({
  model,
  identity,
}: {
  model: MembersPageModel;
  identity?: string | null;
}) {
  const { table, filters, contributions } = model;

  return (
    <main className="page page--1100">
      <div className="page-header">
        <h1>Members</h1>
        <div className="toolbar">
          <button type="button" onClick={model.form.openCreate}>
            Add member
          </button>
          <LogoutControl identity={identity} onLogout={model.auth.logout} />
        </div>
      </div>

      {model.feedback.error && (
        <StatusMessage tone="error">Error: {model.feedback.error}</StatusMessage>
      )}
      {table.listError && (
        <StatusMessage tone="error">Error loading members: {table.listError}</StatusMessage>
      )}
      {model.feedback.success && (
        <StatusMessage tone="success">{model.feedback.success}</StatusMessage>
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

      {model.form.isOpen && <MemberForm form={model.form} />}
      {contributions.available && (
        <ContributionReviewPanel
          requests={contributions.requests}
          loading={contributions.loading}
          onRefresh={contributions.refresh}
          onApprove={contributions.approve}
          onReject={contributions.reject}
        />
      )}
      <MemberTable {...table} />
    </main>
  );
}
