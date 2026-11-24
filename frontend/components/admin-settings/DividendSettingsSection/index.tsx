import type { Settings } from "@/lib/api";
import type { SettingsPageModel } from "../hooks/useSettingsPage";

const BASIS_OPTIONS: { value: Settings["dividend_basis"]; label: string }[] = [
  { value: "none", label: "No basis chosen (runs are refused)" },
  { value: "net_savings_closing", label: "Closing net savings" },
  { value: "net_savings_average", label: "Average net savings across the year" },
  { value: "declared_rate_on_savings", label: "Declared rate on closing savings" },
  { value: "patronage", label: "Loan interest the member paid" },
  { value: "equal", label: "Equal share per eligible member" },
  { value: "hybrid", label: "Hybrid: savings and loan interest" },
];

const POOL_OPTIONS: { value: Settings["dividend_pool_mode"]; label: string }[] = [
  { value: "net_income_share", label: "A share of the year's surplus" },
  { value: "savings_percent", label: "A percentage of total savings" },
  { value: "fixed_amount", label: "A fixed amount set by the committee" },
];

// A basis of "declared rate on savings" divides the pool by savings too, so
// the declared rate only sets the size of the pool in savings-percent mode.
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

export default function DividendSettingsSection({
  settings,
  setField,
}: {
  settings: NonNullable<SettingsPageModel["settings"]>;
  setField: SettingsPageModel["setField"];
}) {
  const split =
    Number(settings.dividend_reserve_pct) +
    Number(settings.dividend_honorarium_pct) +
    Number(settings.dividend_payout_pct);
  const splitBalanced = Math.abs(split - 100) <= 0.01;

  return (
    <section>
      <h2>Dividends</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 0 }}>
        A dividend shares out surplus the cooperative has already earned. Declaring one closes
        the fiscal year in the cashbook first, then splits the surplus into a reserve, an
        honorarium for those who served, and the members&apos; pool.
      </p>

      <label style={{ display: "block", marginBottom: 8 }}>
        Fiscal year opens in
        <select
          value={settings.fiscal_year_start_month}
          onChange={(e) => setField("fiscal_year_start_month", Number(e.target.value))}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          {MONTH_NAMES.map((month, index) => (
            <option key={month} value={index + 1}>
              {month}
            </option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          A run for 2025 covers the twelve months from this month in 2025. Income and expenses
          dated inside that window are what the surplus is measured from.
        </span>
      </label>

      <label style={{ display: "block", marginBottom: 8 }}>
        How a member&apos;s share is measured
        <select
          value={settings.dividend_basis}
          onChange={(e) =>
            setField("dividend_basis", e.target.value as Settings["dividend_basis"])
          }
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          {BASIS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label style={{ display: "block", marginBottom: 8 }}>
        Size of the pool
        <select
          value={settings.dividend_pool_mode}
          onChange={(e) =>
            setField("dividend_pool_mode", e.target.value as Settings["dividend_pool_mode"])
          }
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          {POOL_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      {settings.dividend_pool_mode === "savings_percent" && (
        <label style={{ display: "block", marginBottom: 8 }}>
          Declared rate (% of savings)
          <input
            type="number"
            step="0.01"
            min={0}
            max={100}
            value={settings.dividend_declared_rate_pct ?? ""}
            onChange={(e) => setField("dividend_declared_rate_pct", e.target.value)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
      )}

      {settings.dividend_pool_mode === "fixed_amount" && (
        <label style={{ display: "block", marginBottom: 8 }}>
          Fixed pool amount (₦)
          <input
            type="number"
            step="0.01"
            min={0}
            value={settings.dividend_fixed_pool_amount ?? ""}
            onChange={(e) => setField("dividend_fixed_pool_amount", e.target.value)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
      )}

      <fieldset style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12, marginBottom: 8 }}>
        <legend style={{ fontSize: 14 }}>Split of the year&apos;s surplus</legend>
        <label style={{ display: "block", marginBottom: 8 }}>
          Reserve (%)
          <input
            type="number"
            step="0.01"
            min={0}
            max={100}
            value={settings.dividend_reserve_pct}
            onChange={(e) => setField("dividend_reserve_pct", e.target.value)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
        <label style={{ display: "block", marginBottom: 8 }}>
          Honorarium (%)
          <input
            type="number"
            step="0.01"
            min={0}
            max={100}
            value={settings.dividend_honorarium_pct}
            onChange={(e) => setField("dividend_honorarium_pct", e.target.value)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
        <label style={{ display: "block" }}>
          Members&apos; pool (%)
          <input
            type="number"
            step="0.01"
            min={0}
            max={100}
            value={settings.dividend_payout_pct}
            onChange={(e) => setField("dividend_payout_pct", e.target.value)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
        </label>
        <span
          style={{
            display: "block",
            marginTop: 8,
            fontSize: 12,
            color: splitBalanced ? "var(--text-muted)" : "#a33",
          }}
        >
          Reserve + honorarium + pool = {split.toFixed(2)}%. The three must add up to 100.
        </span>
      </fieldset>

      {settings.dividend_basis === "hybrid" && (
        <label style={{ display: "block", marginBottom: 8 }}>
          Weight on savings (%)
          <input
            type="number"
            step="0.01"
            min={0}
            max={100}
            value={settings.dividend_hybrid_savings_pct}
            onChange={(e) => setField("dividend_hybrid_savings_pct", e.target.value)}
            style={{ display: "block", padding: 8, marginTop: 4 }}
          />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            The rest of the weight goes to loan interest the member paid during the year.
          </span>
        </label>
      )}

      <label style={{ display: "block", marginBottom: 8 }}>
        Minimum months of membership
        <input
          type="number"
          min={0}
          value={settings.dividend_min_membership_months}
          onChange={(e) =>
            setField("dividend_min_membership_months", parseInt(e.target.value) || 0)
          }
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          0 includes every eligible member, however recently they joined.
        </span>
      </label>

      <label style={{ display: "block", marginBottom: 8 }}>
        <input
          type="checkbox"
          checked={settings.dividend_include_exited}
          onChange={(e) => setField("dividend_include_exited", e.target.checked)}
        />{" "}
        Include members who left during the year (their share follows the exit settlement)
      </label>

      <label style={{ display: "block", marginBottom: 8 }}>
        Rounding
        <select
          value={settings.dividend_rounding}
          onChange={(e) =>
            setField("dividend_rounding", e.target.value as Settings["dividend_rounding"])
          }
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          <option value="two_dp">To the kobo</option>
          <option value="whole_currency">To the whole naira</option>
        </select>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          The pool is shared out exactly; the leftover kobo or naira is spread so the paid total
          matches the pool.
        </span>
      </label>

      <label style={{ display: "block", marginBottom: 8 }}>
        Withholding tax (%)
        <input
          type="number"
          step="0.01"
          min={0}
          max={100}
          value={settings.dividend_withholding_pct}
          onChange={(e) => setField("dividend_withholding_pct", e.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        />
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Deducted from each member&apos;s dividend and held as a payable. 0 turns withholding
          off.
        </span>
      </label>

      <label style={{ display: "block" }}>
        How dividends are paid
        <select
          value={settings.dividend_payment_method}
          onChange={(e) =>
            setField(
              "dividend_payment_method",
              e.target.value as Settings["dividend_payment_method"]
            )
          }
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          <option value="bank">Bank transfer only</option>
          <option value="cash">Cash only</option>
          <option value="either">Either cash or bank</option>
        </select>
      </label>
    </section>
  );
}
