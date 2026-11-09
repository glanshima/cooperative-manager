import StatusMessage from "@/components/ui/StatusMessage";
import type { MembersPageModel } from "../hooks/useMembersPage";
import MemberFilters from "../MemberFilters";
import MemberForm from "../MemberForm";
import MemberSearch from "../MemberSearch";
import MemberTable from "../MemberTable";
import ContributionReviewPanel from "../ContributionReviewPanel";

export default function MembersView({ model }: { model: MembersPageModel }) {
  const { table, filters, contributions } = model;

  return (
    <main style={{ padding: 32, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Members</h1>
        <button onClick={model.auth.logout}>Log out</button>
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

      <MemberForm form={model.form} />
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
