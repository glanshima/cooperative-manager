import { formatMoney } from "@/components/deductions/labels";
import Modal from "@/components/ui/Modal";
import Table from "@/components/ui/Table";

import type { DividendsPageModel } from "../hooks/useDividendsPage";

export default function ManifestModal({ model }: { model: DividendsPageModel }) {
  if (!model.manifest.open || !model.manifest.data) return null;

  const manifest = model.manifest.data;

  return (
    <Modal
      title={`${manifest.fiscal_year} dividend manifest`}
      onClose={model.closeManifest}
      maxWidth={900}
    >
      <p style={{ margin: "0 0 12px", color: "var(--text-muted)", fontSize: 13 }}>
        Reference {manifest.reference}. Every row shows the dividend before withholding, the tax
        held, and the amount to hand the member.
      </p>
      <Table>
        <thead>
          <tr>
            <th>PSN</th>
            <th>Member</th>
            <th>Bank</th>
            <th>Account</th>
            <th>Gross</th>
            <th>Withholding</th>
            <th>Net</th>
          </tr>
        </thead>
        <tbody>
          {manifest.rows.map((row) => (
            <tr key={row.psn}>
              <td>{row.psn}</td>
              <td>{row.name}</td>
              <td>{row.bank_name || "—"}</td>
              <td>{row.account_number || "—"}</td>
              <td>₦{formatMoney(row.gross_amount)}</td>
              <td>₦{formatMoney(row.withholding_amount)}</td>
              <td>₦{formatMoney(row.net_amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th colSpan={4}>Totals</th>
            <th>₦{formatMoney(manifest.total_gross)}</th>
            <th>₦{formatMoney(manifest.total_withholding)}</th>
            <th>₦{formatMoney(manifest.total_net)}</th>
          </tr>
        </tfoot>
      </Table>
      <div className="toolbar toolbar--end" style={{ marginTop: 12 }}>
        <button type="button" onClick={model.closeManifest}>
          Close
        </button>
      </div>
    </Modal>
  );
}
