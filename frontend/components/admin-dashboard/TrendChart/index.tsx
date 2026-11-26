import type { DashboardTrend } from "@/lib/api";
import { formatMoney } from "@/components/deductions/labels";

import styles from "./TrendChart.module.css";

const WIDTH = 640;
const HEIGHT = 220;
const BASE = 190;
const PLOT_HEIGHT = 166;
const BAR_WIDTH = 28;
const BAR_GAP = 8;

function monthLabel(key: string, showYear: boolean): string {
  const [year, month] = key.split("-").map(Number);
  const name = new Date(year, month - 1, 1).toLocaleString(undefined, { month: "short" });
  return showYear ? `${name} ${String(year).slice(2)}` : name;
}

export default function TrendChart({ trend }: { trend: DashboardTrend }) {
  const series = [
    trend.savings ? { key: "savings", label: "Savings", values: trend.savings } : null,
    trend.repayments
      ? { key: "repayments", label: "Verified repayments", values: trend.repayments }
      : null,
  ].filter((item): item is NonNullable<typeof item> => item !== null);

  const peak = Math.max(0, ...series.flatMap((item) => item.values.map(Number)));
  const count = trend.months.length;
  const slot = WIDTH / count;
  const block = series.length * BAR_WIDTH + (series.length - 1) * BAR_GAP;

  if (!peak) {
    return (
      <p className={styles.empty}>
        No savings or verified repayments in the last six months.
      </p>
    );
  }

  return (
    <>
      <div className={styles.legend}>
        {series.map((item) => (
          <span key={item.key} className={styles.legendItem}>
            <span
              className={styles.swatch}
              style={{ background: item.key === "savings" ? "var(--primary)" : "var(--success)" }}
              aria-hidden="true"
            />
            {item.label}
          </span>
        ))}
      </div>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Monthly savings and verified repayments over the last six months"
      >
        <text x="0" y="12" className={styles.axisLabel}>
          ₦{formatMoney(peak)}
        </text>
        {trend.months.map((month, position) => {
          const slotStart = position * slot;
          const blockStart = slotStart + (slot - block) / 2;
          return (
            <g key={month}>
              {series.map((item, index) => {
                const height = (Number(item.values[position]) / peak) * PLOT_HEIGHT;
                return (
                  <rect
                    key={item.key}
                    x={blockStart + index * (BAR_WIDTH + BAR_GAP)}
                    y={BASE - height}
                    width={BAR_WIDTH}
                    height={height}
                    rx="2"
                    fill={item.key === "savings" ? "var(--primary)" : "var(--success)"}
                  />
                );
              })}
              <text x={slotStart + slot / 2} y={BASE + 18} textAnchor="middle" className={styles.axisLabel}>
                {monthLabel(month, position === 0 || month.endsWith("-01"))}
              </text>
            </g>
          );
        })}
      </svg>
      <div className={styles.visuallyHidden}>
        <table>
          <caption>Last six months by month</caption>
          <thead>
            <tr>
              <th scope="col">Month</th>
              {series.map((item) => (
                <th key={item.key} scope="col">
                  {item.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trend.months.map((month, position) => (
              <tr key={month}>
                <th scope="row">{month}</th>
                {series.map((item) => (
                  <td key={item.key}>₦{formatMoney(item.values[position])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
