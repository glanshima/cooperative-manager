import styles from "./CloseButton.module.css";

/** The one close control: an icon button whose name is still announced. */
export default function CloseButton({
  onClick,
  label = "Close",
  disabled = false,
  size = "md",
}: {
  onClick: () => void;
  label?: string;
  disabled?: boolean;
  size?: "sm" | "md";
}) {
  return (
    <button
      type="button"
      className={styles.button}
      data-size={size}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      <span aria-hidden="true">&times;</span>
    </button>
  );
}
