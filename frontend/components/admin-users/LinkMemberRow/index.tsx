import type { CurrentUser, Member } from "@/lib/api";
import type { AdminUsersPageModel } from "../hooks/useAdminUsersPage";
import MemberPicker from "../MemberPicker";
import { describeMember } from "../utils";

export default function LinkMemberRow({
  user,
  linkedMember,
  link,
}: {
  user: CurrentUser;
  linkedMember?: Member;
  link: AdminUsersPageModel["table"]["link"];
}) {
  return (
    <tr>
      <td colSpan={6} style={{ padding: 12, background: "#fafafa" }}>
        <strong>
          {user.member_id ? `Change ${user.username}'s linked member` : `Link ${user.username} to a member`}
        </strong>
        {user.member_id && linkedMember && (
          <p style={{ margin: "4px 0", color: "#555" }}>
            Currently linked to: <strong>{describeMember(linkedMember)}</strong>
          </p>
        )}
        {link.selected ? (
          <p>
            New selection: <strong>{describeMember(link.selected)}</strong>{" "}
            <button type="button" onClick={link.clear}>
              Change selection
            </button>
          </p>
        ) : (
          <MemberPicker
            query={link.query}
            results={link.results}
            onQueryChange={link.setQuery}
            onSearch={link.search}
            onSelect={link.select}
            style={{ marginTop: 8 }}
          />
        )}
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button onClick={() => link.confirm(user)} disabled={!link.selected}>
            Confirm {user.member_id ? "change" : "link"}
          </button>
          <button onClick={link.close}>Cancel</button>
        </div>
      </td>
    </tr>
  );
}
