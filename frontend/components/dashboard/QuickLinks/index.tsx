import DashboardIcon from "../icons";
import type { DashboardIconName } from "../icons";
import styles from "../dashboard.module.css";

export default function QuickLinks({
  loansEnabled,
  onApplyForLoan,
}: {
  loansEnabled: boolean;
  onApplyForLoan: () => void;
}) {
  const links: Array<{
    href: string;
    label: string;
    icon: DashboardIconName;
    onClick?: () => void;
  }> = [];

  if (loansEnabled) {
    links.push(
      { href: "#loans", label: "Apply for a loan", icon: "plus", onClick: onApplyForLoan },
      { href: "#loans", label: "Make a repayment", icon: "loans" }
    );
  }
  links.push(
    { href: "#savings", label: "Request a savings change", icon: "contribution" },
    { href: "#preferences", label: "Notification settings", icon: "settings" }
  );

  return (
    <section className={styles.panel}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>Quick actions</h2>
      </div>
      <div className={styles.quickList}>
        {links.map((link) => (
          <a key={link.label} href={link.href} className={styles.quickLink} onClick={link.onClick}>
            <span className={styles.quickIcon}>
              <DashboardIcon name={link.icon} size={17} />
            </span>
            <span className={styles.quickLabel}>{link.label}</span>
            <span className={styles.quickChevron}>
              <DashboardIcon name="chevron" size={15} />
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
