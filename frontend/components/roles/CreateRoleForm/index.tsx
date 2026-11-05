import type { RolesPageModel } from "../hooks/useRolesPage";

export default function CreateRoleForm({ create }: { create: RolesPageModel["create"] }) {
  return (
    <form
      onSubmit={create.submit}
      style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 24 }}
    >
      <label>
        Role name
        <input
          value={create.name}
          onChange={(e) => create.setName(e.target.value)}
          required
          style={{ display: "block", padding: 8 }}
        />
      </label>
      <label>
        Description
        <input
          value={create.description}
          onChange={(e) => create.setDescription(e.target.value)}
          style={{ display: "block", padding: 8 }}
        />
      </label>
      <label style={{ paddingBottom: 8 }}>
        <input
          type="checkbox"
          checked={create.requiresMemberLink}
          onChange={(e) => create.setRequiresMemberLink(e.target.checked)}
        />{" "}
        Requires Member link
      </label>
      <button type="submit">Add role</button>
    </form>
  );
}
