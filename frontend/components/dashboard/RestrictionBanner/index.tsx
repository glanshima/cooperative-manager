import type { Settings } from "@/lib/api";

export default function RestrictionBanner({ settings }: { settings: Settings | null }) {
  return (
    <div
      style={{
        background: "#fff3cd",
        border: "1px solid #ffe69c",
        borderRadius: 6,
        padding: 12,
        marginBottom: 16,
      }}
    >
      Your account currently has a loan restriction noted by the cooperative.
      {settings?.loan_restriction_behavior === "block"
        ? " You won't be able to submit new applications until this is resolved."
        : " You can still apply, but this will be flagged for the reviewing admin."}
    </div>
  );
}
