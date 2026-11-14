import { Children, cloneElement, isValidElement } from "react";
import type { CSSProperties, ReactElement, ReactNode } from "react";

type ElementWithChildren = ReactElement<{ children?: ReactNode }>;

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

function isHost(node: ReactNode, type: string): node is ElementWithChildren {
  return isValidElement(node) && node.type === type;
}

// Phone layout turns each row into a card, so every cell needs the column
// heading it belongs to. Reading the thead here keeps that behaviour in one
// place instead of asking all fourteen tables to repeat data-label props.
function headerLabels(children: ReactNode): string[] {
  let labels: string[] = [];
  Children.forEach(children, (section) => {
    if (!isHost(section, "thead")) return;
    const row = Children.toArray(section.props.children).find((child) => isHost(child, "tr"));
    if (!row || !isHost(row, "tr")) return;
    labels = Children.toArray(row.props.children).map((cell) =>
      isHost(cell, "th") ? textOf(cell.props.children).trim() : ""
    );
  });
  return labels;
}

function labelCells(children: ReactNode, labels: string[]): ReactNode {
  return Children.map(children, (section) => {
    if (!isHost(section, "tbody")) return section;
    const rows = Children.map(section.props.children, (row) => {
      if (!isHost(row, "tr")) return row;
      return cloneElement(
        row,
        {},
        Children.map(row.props.children, (cell, index) => {
          const label = labels[index];
          if (!label || !isValidElement(cell)) return cell;
          // Rows that span the table (e.g. an inline edit form) already carry
          // their own heading, so a single column label would mislead.
          if ((cell.props as { colSpan?: number }).colSpan) return cell;
          return cloneElement(cell as ReactElement<{ "data-label"?: string }>, {
            "data-label": label,
          });
        })
      );
    });
    return cloneElement(section, {}, rows);
  });
}

export default function Table({
  children,
  style,
}: {
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div className="table-scroll">
      <table className="data-table" style={style}>
        {labelCells(children, headerLabels(children))}
      </table>
    </div>
  );
}
