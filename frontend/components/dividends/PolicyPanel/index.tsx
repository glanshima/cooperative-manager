import StatusMessage from "@/components/ui/StatusMessage";

import type { DividendsPageModel } from "../hooks/useDividendsPage";
import { BASIS_LABELS, PAYMENT_POLICY_LABELS, POOL_LABELS, ROUNDING_LABELS } from "../labels";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export default function PolicyPanel({ model }: { model: DividendsPageModel }) {
  const summary = model.summary;
  if (!summary) return null;

  return (
    <section aria-label="Dividend policy">
      <h2 style={{ marginBottom: 8 }}>Policy in effect</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 0 }}>
        A draft is computed from these figures; declaring a dividend freezes them. Change them in
        Cooperative settings and recompute a draft to apply a new policy.
      </p>
      <dl className="detail-grid">
        <div>
          <dt>Fiscal year starts</dt>
          <dd>{MONTH_NAMES[summary.fiscal_year_start_month - 1] ?? "January"}</dd>
        </div>
        <div>
          <dt>Member share measured by</dt>
          <dd>{BASIS_LABELS[summary.basis]}</dd>
        </div>
        <div>
          <dt>Pool size</dt>
          <dd>{POOL_LABELS[summary.pool_mode]}</dd>
        </div>
        <div>
          <dt>Surplus split</dt>
          <dd>
            {Number(summary.reserve_pct).toFixed(2)}% reserve ·{" "}
            {Number(summary.honorarium_pct).toFixed(2)}% honorarium ·{" "}
            {Number(summary.payout_pct).toFixed(2)}% members
          </dd>
        </div>
        <div>
          <dt>Rounding</dt>
          <dd>{ROUNDING_LABELS[summary.rounding]}</dd>
        </div>
        <div>
          <dt>Withholding</dt>
          <dd>{Number(summary.withholding_pct).toFixed(2)}%</dd>
        </div>
        <div>
          <dt>Payout method</dt>
          <dd>{PAYMENT_POLICY_LABELS[summary.payment_method]}</dd>
        </div>
        <div>
          <dt>Last declared year</dt>
          <dd>{summary.last_declared_year ?? "None yet"}</dd>
        </div>
      </dl>

      {!summary.cashbook_module_enabled && (
        <StatusMessage tone="error">
          The Cashbook module is off. A dividend cannot be declared until an administrator turns
          the cashbook on and the opening balances are posted.
        </StatusMessage>
      )}
      {summary.cashbook_module_enabled && !summary.cashbook_open && (
        <StatusMessage tone="error">
          The cashbook has no opening balances yet. Post them on the Cashbook screen before
          declaring a dividend, because declaring closes the fiscal year in the books.
        </StatusMessage>
      )}
    </section>
  );
}
