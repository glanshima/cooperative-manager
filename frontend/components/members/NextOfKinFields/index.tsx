import type { MembersPageModel } from "../hooks/useMembersPage";
import { describeMemberOption } from "../utils";

export default function NextOfKinFields({ form }: { form: MembersPageModel["form"] }) {
  const { nok } = form;

  return (
    <>
      <div style={{ gridColumn: "1 / -1", fontWeight: 600, marginTop: 8 }}>
        Next of kin{form.editingId ? "" : " *"}
      </div>

      {/* This Yes/No question is required for a NEW member (checked in
          the hook's submit handler); for an existing legacy member it may
          start unanswered if next_of_kin_is_member is null, and stays
          that way until the person editing explicitly picks one. */}
      <div style={{ gridColumn: "1 / -1" }}>
        <label style={{ marginRight: 16 }}>
          <input
            type="radio"
            name="nokIsMember"
            checked={nok.isMember === true}
            onChange={() => nok.chooseIsMember(true)}
          />{" "}
          Next of kin is a cooperative member
        </label>
        <label>
          <input
            type="radio"
            name="nokIsMember"
            checked={nok.isMember === false}
            onChange={() => nok.chooseIsMember(false)}
          />{" "}
          Next of kin is not a cooperative member
        </label>
      </div>

      {nok.isMember === true && (
        <div style={{ gridColumn: "1 / -1" }}>
          {nok.selected ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>
                Selected: <strong>{describeMemberOption(nok.selected)}</strong>
              </span>
              <button type="button" onClick={nok.clearSelected}>
                Change
              </button>
            </div>
          ) : (
            <div>
              <input
                placeholder="Search member by PSN, name, or phone"
                value={nok.query}
                onChange={(e) => nok.setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), nok.search())}
                style={{ marginRight: 8 }}
              />
              <button type="button" onClick={nok.search}>
                Search
              </button>
              {nok.results.length > 0 && (
                <ul style={{ listStyle: "none", padding: 0, margin: "8px 0" }}>
                  {nok.results.map((m) => (
                    <li key={m.id}>
                      <button type="button" onClick={() => nok.select(m)}>
                        {describeMemberOption(m)}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {nok.isMember === false && (
        <>
          <input
            placeholder="Next of kin name"
            value={form.values.next_of_kin}
            onChange={(e) => form.setField("next_of_kin", e.target.value)}
          />
          <input
            placeholder="Next of kin phone"
            value={form.values.next_of_kin_phone}
            onChange={(e) => form.setField("next_of_kin_phone", e.target.value)}
          />
          <input
            placeholder="Next of kin address"
            value={form.values.next_of_kin_address}
            onChange={(e) => form.setField("next_of_kin_address", e.target.value)}
          />
          <input
            placeholder="Next of kin email"
            value={form.values.next_of_kin_email}
            onChange={(e) => form.setField("next_of_kin_email", e.target.value)}
          />
          <input
            placeholder="Relationship (e.g. Spouse, Sibling)"
            value={form.values.next_of_kin_relationship}
            onChange={(e) => form.setField("next_of_kin_relationship", e.target.value)}
          />
        </>
      )}
    </>
  );
}
