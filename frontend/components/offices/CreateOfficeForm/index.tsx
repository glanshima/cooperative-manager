import type { OfficesPageModel } from "../hooks/useOfficesPage";

export default function CreateOfficeForm({ form }: { form: OfficesPageModel["form"] }) {
  return (
    <form
      onSubmit={form.submit}
      style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 24 }}
    >
      <label>
        Name
        <input
          value={form.name}
          onChange={(e) => form.setName(e.target.value)}
          required
          style={{ display: "block", padding: 8 }}
        />
      </label>
      <label>
        Description
        <input
          value={form.description}
          onChange={(e) => form.setDescription(e.target.value)}
          style={{ display: "block", padding: 8 }}
        />
      </label>
      <button type="submit">Add office</button>
    </form>
  );
}
