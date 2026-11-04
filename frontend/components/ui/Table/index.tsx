import type { CSSProperties, ReactNode } from "react";

export default function Table({
  children,
  style,
}: {
  children: ReactNode;
  style?: CSSProperties;
}) {
  return <table style={{ width: "100%", borderCollapse: "collapse", ...style }}>{children}</table>;
}
