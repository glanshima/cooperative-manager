import { formatMoney } from "@/components/deductions/labels";
import Pagination from "@/components/ui/Pagination";
import Table from "@/components/ui/Table";

import type { DividendsPageModel } from "../hooks/useDividendsPage";
import {
  BASIS_LABELS,
  PAYOUT_METHOD_LABELS,
  ROUNDING_LABELS,
  RUN_STATUS_COLORS,
  RUN_STATUS_LABELS,
  formatBasis,
  todayIso,
} from "../labels";

export default function RunDetail({ model }: { model: DividendsPageModel }) {
  const { detail } = model;

  if (!detail) {
    return (
      <p style={{ color: "var(--text-muted)" }}>
        {model.detailLoading ? (
          "Loading the run…"
        ) : (
          <>
            The run could not be loaded.{" "}
            <button type="button" className="link-button" onClick={model.closeRun}>
              Back to all runs
            </button>
          </>
        )}
      </p>
    );
  }

  const run = detail.run;
  const yearEnded = run.period_end <= todayIso();
  const canPayThisRun =
    model.permissions.canPay && run.status === "declared" && detail.pending_allocations > 0;

  return (
    <>
      <button type="button" className="link-button" disabled={model.busy} onClick={model.closeRun}>
        ← All runs
      </button>

      <div className="toolbar" style={{ marginTop: 8, alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>{run.fiscal_year} dividend</h2>
        <span style={{ color: RUN_STATUS_COLORS[run.status], fontWeight: 600 }}>
          {RUN_STATUS_LABELS[run.status]}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
          {run.status === "draft" && model.permissions.canDeclare && (
            <>
              <button type="button" disabled={model.busy} onClick={model.recompute}>
                Recompute
              </button>
              <button
                type="button"
                disabled={model.busy || !yearEnded}
                title={
                  yearEnded
                    ? undefined
                    : `The fiscal year ends on ${run.period_end}. A dividend is declared once the year is over.`
                }
                onClick={model.openDeclare}
              >
                Declare
              </button>
              <button
                type="button"
                disabled={model.busy}
                onClick={() => model.setDeleteTarget(run)}
              >
                Delete draft
              </button>
            </>
          )}
          <button type="button" disabled={model.busy} onClick={model.openManifest}>
            Manifest
          </button>
          {canPayThisRun && (
            <button type="button" disabled={model.busy} onClick={model.openPayout}>
              Record payout
            </button>
          )}
        </div>
      </div>

      {run.status === "draft" && model.permissions.canDeclare && !yearEnded && (
        <p style={{ fontSize: 14, color: "var(--text-muted)", marginTop: 0 }}>
          The fiscal year ends on {run.period_end}. The dividend can be declared once the year is
          over.
        </p>
      )}

      <dl className="detail-grid">
        <div>
          <dt>Period</dt>
          <dd>
            {run.period_start} – {run.period_end}
          </dd>
        </div>
        <div>
          <dt>Surplus for the year</dt>
          <dd>₦{formatMoney(run.surplus)}</dd>
        </div>
        <div>
          <dt>Reserve ({Number(run.reserve_pct).toFixed(2)}%)</dt>
          <dd>₦{formatMoney(run.reserve_amount)}</dd>
        </div>
        <div>
          <dt>Honorarium ({Number(run.honorarium_pct).toFixed(2)}%)</dt>
          <dd>₦{formatMoney(run.honorarium_amount)}</dd>
        </div>
        <div>
          <dt>Members&apos; pool</dt>
          <dd>₦{formatMoney(run.pool_amount)}</dd>
        </div>
        <div>
          <dt>Eligible members</dt>
          <dd>{run.eligible_member_count}</dd>
        </div>
        <div>
          <dt>Total gross</dt>
          <dd>₦{formatMoney(run.total_gross)}</dd>
        </div>
        <div>
          <dt>Withholding ({Number(run.withholding_pct).toFixed(2)}%)</dt>
          <dd>₦{formatMoney(run.total_withholding)}</dd>
        </div>
        <div>
          <dt>Net payable</dt>
          <dd>₦{formatMoney(run.total_net)}</dd>
        </div>
        <div>
          <dt>Share measured by</dt>
          <dd>{BASIS_LABELS[run.basis]}</dd>
        </div>
        <div>
          <dt>Rounding</dt>
          <dd>
            {ROUNDING_LABELS[run.rounding]} (residual ₦{formatMoney(run.rounding_residual)})
          </dd>
        </div>
        <div>
          <dt>Declared on</dt>
          <dd>{run.declared_on ?? "Not declared"}</dd>
        </div>
        {run.note && (
          <div>
            <dt>Note</dt>
            <dd>{run.note}</dd>
          </div>
        )}
      </dl>

      {detail.payouts.length > 0 && (
        <section aria-label="Payouts" style={{ marginTop: 24 }}>
          <h3 style={{ margin: "0 0 8px" }}>Payout batches</h3>
          <Table>
            <thead>
              <tr>
                <th>Paid on</th>
                <th>Method</th>
                <th>Reference</th>
                <th>Amount</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {detail.payouts.map((payout) => (
                <tr key={payout.id}>
                  <td>{payout.paid_on}</td>
                  <td>{PAYOUT_METHOD_LABELS[payout.method]}</td>
                  <td>{payout.reference}</td>
                  <td>₦{formatMoney(payout.amount)}</td>
                  <td>{payout.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </section>
      )}

      <section aria-label="Allocations" style={{ marginTop: 24 }}>
        <h3 style={{ margin: "0 0 8px" }}>Allocations</h3>
        <div className="toolbar" style={{ marginBottom: 12 }}>
          <input
            aria-label="Search allocations"
            placeholder="PSN or member name"
            value={model.search}
            onChange={(e) => model.setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                model.applySearch();
              }
            }}
            disabled={model.allocationsLoading}
          />
          <button
            type="button"
            onClick={() => {
              void model.applySearch();
            }}
            disabled={model.allocationsLoading}
          >
            Search
          </button>
          {model.appliedSearch && (
            <button
              type="button"
              disabled={model.allocationsLoading}
              onClick={() => {
                void model.applySearch("");
              }}
            >
              Clear search
            </button>
          )}
          {model.selectedCount > 0 && (
            <span style={{ marginLeft: "auto", fontSize: 13 }}>
              {model.selectedCount} selected · ₦{formatMoney(model.selectedAmount)}
            </span>
          )}
        </div>

        {model.allocationsLoading && <p style={{ color: "var(--text-muted)" }}>Loading…</p>}

        {model.allocations && model.allocations.items.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
            {model.appliedSearch
              ? "No member matches that search."
              : "No member is eligible under the policy this run was computed with."}
          </p>
        ) : null}

        {model.allocations && model.allocations.items.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <th style={{ width: 32 }} aria-label="Select" />
                  <th>PSN</th>
                  <th>Member</th>
                  <th>Basis</th>
                  <th>Share</th>
                  <th>Gross</th>
                  <th>Withholding</th>
                  <th>Net</th>
                  <th>Paid</th>
                </tr>
              </thead>
              <tbody>
                {model.allocations.items.map((row) => {
                  const paid = Boolean(row.payout_id);
                  const selectable = !paid && canPayThisRun && !model.busy;
                  return (
                    <tr key={row.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select ${row.psn}`}
                          checked={model.isSelected(row.id)}
                          disabled={!selectable}
                          onChange={() => model.toggleSelected(row)}
                        />
                      </td>
                      <td>{row.psn}</td>
                      <td>{row.name}</td>
                      <td>
                        {run.basis === "hybrid"
                          ? formatBasis(run.basis, row.basis_amount)
                          : `₦${formatMoney(row.basis_amount)}`}
                      </td>
                      <td>{(Number(row.share_ratio) * 100).toFixed(2)}%</td>
                      <td>₦{formatMoney(row.gross_amount)}</td>
                      <td>₦{formatMoney(row.withholding_amount)}</td>
                      <td>₦{formatMoney(row.net_amount)}</td>
                      <td>
                        {paid ? (
                          <span style={{ color: "green", fontWeight: 600 }}>Paid</span>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>

            <Pagination
              skip={model.allocations.skip}
              limit={model.allocations.limit}
              total={model.allocations.total}
              onChange={model.changePage}
            />
          </>
        )}

        {run.status === "declared" && (
          <p style={{ fontSize: 14, color: "var(--text-muted)" }}>
            {detail.paid_allocations} of {detail.paid_allocations + detail.pending_allocations}{" "}
            allocations paid. Pending: ₦{formatMoney(model.pendingAmount)}.
            {!model.permissions.canPay &&
              detail.pending_allocations > 0 &&
              " Recording payouts needs the dividend.pay permission."}
          </p>
        )}
      </section>
    </>
  );
}
