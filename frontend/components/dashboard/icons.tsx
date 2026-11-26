export type DashboardIconName =
  | "overview"
  | "savings"
  | "loans"
  | "activity"
  | "contribution"
  | "notifications"
  | "settings"
  | "plus"
  | "check"
  | "chevron"
  | "calendar";

// One inline set so the dashboard draws no icon-font or image requests.
export default function DashboardIcon({
  name,
  size = 18,
}: {
  name: DashboardIconName;
  size?: number;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  switch (name) {
    case "overview":
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
          <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
          <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
          <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
        </svg>
      );
    case "savings":
      return (
        <svg {...common}>
          <path d="M3 21h18" />
          <path d="M5 18h14" />
          <path d="M6.5 18v-6" />
          <path d="M10.5 18v-6" />
          <path d="M13.5 18v-6" />
          <path d="M17.5 18v-6" />
          <path d="M12 3l8 4.5H4L12 3z" />
        </svg>
      );
    case "loans":
      return (
        <svg {...common}>
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
          <path d="M2.5 10h19" />
          <path d="M6.5 15h4" />
        </svg>
      );
    case "activity":
      return (
        <svg {...common}>
          <path d="M3 12h4l2.5-6.5 4.5 13 2.5-6.5H21" />
        </svg>
      );
    case "contribution":
      return (
        <svg {...common}>
          <path d="M3 12a9 9 0 0 1 15.5-6.2L21 8" />
          <path d="M21 3v5h-5" />
          <path d="M21 12a9 9 0 0 1-15.5 6.2L3 16" />
          <path d="M3 21v-5h5" />
        </svg>
      );
    case "notifications":
      return (
        <svg {...common}>
          <path d="M18 8.5a6 6 0 1 0-12 0c0 6.5-2.5 6.5-2.5 8.5h17c0-2-2.5-2-2.5-8.5" />
          <path d="M10.3 21a2 2 0 0 0 3.4 0" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common}>
          <path d="M4 7h9" />
          <path d="M17 7h3" />
          <circle cx="15" cy="7" r="2" />
          <path d="M4 12h3" />
          <path d="M11 12h9" />
          <circle cx="9" cy="12" r="2" />
          <path d="M4 17h9" />
          <path d="M17 17h3" />
          <circle cx="15" cy="17" r="2" />
        </svg>
      );
    case "plus":
      return (
        <svg {...common}>
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </svg>
      );
    case "check":
      return (
        <svg {...common}>
          <path d="M20 6 9 17l-5-5" />
        </svg>
      );
    case "chevron":
      return (
        <svg {...common}>
          <path d="m9 6 6 6-6 6" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M16 3v4" />
          <path d="M8 3v4" />
          <path d="M3 11h18" />
        </svg>
      );
  }
}
