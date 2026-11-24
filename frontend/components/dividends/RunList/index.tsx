import { formatMoney } from "@/components/deductions/labels";
import Table from "@/components/ui/Table";

import type { DividendsPageModel } from "../hooks/useDividendsPage";
import { RUN_STATUS_COLORS, RUN_STATUS_LABELS } from "../labels";
import PolicyPanel from "../PolicyPanel";

export default function RunList({ model }: { model: DividendsPageModel }) {
  return (
    <>
      <PolicyPanel model={model} />

      <div className="toolbar" style={{ marginTop: 24 }}>
        <h2 style={{ margin: 0 }}>Fiscal year runs</h2>
        {model.permissions.canDeclare && (
          <button type="button" style={{ marginLeft: "auto" }} onClick={model.openNewRun}>
            New draft run
          </button>
        )}
      </div>

      {model.runs.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          No dividend run has been prepared yet.
          {model.permissions.canDeclare
            ? " Prepare a draft for the first fiscal year to share out its surplus."
            : ""}
        </p>
      ) : (
        <Table>
          <thead>
            <tr>
              <th>Fiscal year</th>
              <th>Period</th>
              <th>Status</th>
              <th>Surplus</th>
              <th>Pool</th>
              <th>Members</th>
              <th>Net payable</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {model.runs.map((run) => (
              <tr key={run.id}>
                <td>{run.fiscal_year}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {run.period_start} – {run.period_end}
                </td>
                <td>
                  <span style={{ color: RUN_STATUS_COLORS[run.status], fontWeight: 600 }}>
                    {RUN_STATUS_LABELS[run.status]}
                  </span>
                </td>
                <td>₦{formatMoney(run.surplus)}</td>
                <td>₦{formatMoney(run.pool_amount)}</td>
                <td>{run.eligible_member_count}</td>
                <td>₦{formatMoney(run.total_net)}</td>
                <td>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => model.openRun(run.id)}
                  >
                    Open
                  </button>
                  {run.status === "draft" && model.permissions.canDeclare && (
                    <button
                      type="button"
                      className="link-button"
                      style={{ marginLeft: 12 }}
                      onClick={() => model.setDeleteTarget(run)}
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
