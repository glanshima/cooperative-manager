import type { AdminUsersPageModel } from "../hooks/useAdminUsersPage";
import MemberPicker from "../MemberPicker";
import { describeMember } from "../utils";

export default function CreateStaffForm({
  create,
  membersEnabled,
}: {
  create: AdminUsersPageModel["create"];
  membersEnabled: boolean;
}) {
  const { member } = create;

  return (
    <section style={{ marginTop: 24 }}>
      <h2>Create staff account</h2>
      <p style={{ color: "#555", fontSize: 14 }}>
        New accounts start with no permissions. Assign a Role below (with an optional Office) so the
        account can actually do anything.
      </p>
      <form
        onSubmit={create.submit}
        style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}
      >
        <label>
          Username
          <input
            value={create.username}
            onChange={(e) => create.setUsername(e.target.value)}
            required
            style={{ display: "block", padding: 8 }}
          />
        </label>
        <label>
          Temporary password
          <input
            type="password"
            value={create.password}
            onChange={(e) => create.setPassword(e.target.value)}
            required
            style={{ display: "block", padding: 8 }}
          />
        </label>
        <button type="submit">Create</button>
      </form>

      <div style={{ marginTop: 12, padding: 12, border: "1px solid #ddd", maxWidth: 480 }}>
        <strong>Optional: link to an existing Member</strong>
        {!membersEnabled ? (
          <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>
            Member linking is unavailable while the Members module is disabled.
          </p>
        ) : (
          <>
            <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>
              Only needed if this staff member is also an elected officer / cooperative member (e.g. Treasurer).
              Not required otherwise.
            </p>
            {member.selected ? (
              <p>
                Selected: <strong>{describeMember(member.selected)}</strong>{" "}
                <button type="button" onClick={member.clear}>
                  Clear
                </button>
              </p>
            ) : (
              <MemberPicker
                query={member.query}
                results={member.results}
                onQueryChange={member.setQuery}
                onSearch={member.search}
                onSelect={member.select}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}
