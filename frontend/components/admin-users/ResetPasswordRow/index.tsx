import type { CurrentUser } from "@/lib/api";

export default function ResetPasswordRow({
  user,
  tempPassword,
  onTempPasswordChange,
  onConfirm,
  onCancel,
}: {
  user: CurrentUser;
  tempPassword: string;
  onTempPasswordChange: (value: string) => void;
  onConfirm: (userId: string) => void;
  onCancel: () => void;
}) {
  return (
    <tr>
      <td colSpan={6} style={{ padding: 12, background: "#fafafa" }}>
        <strong>Reset password for {user.username}</strong>
        <p style={{ color: "#666", fontSize: 13, margin: "4px 0" }}>
          Sets a temporary password and forces the user to choose a new password on their next login.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onConfirm(user.id);
          }}
          style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}
        >
          <input
            type="password"
            placeholder="Temporary password (min 8 chars, 1 letter, 1 number)"
            value={tempPassword}
            onChange={(e) => onTempPasswordChange(e.target.value)}
            required
            style={{ padding: 6, width: 320 }}
          />
          <button type="submit" disabled={!tempPassword}>
            Confirm Reset
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        </form>
      </td>
    </tr>
  );
}
