"use client";

import { useId, useState, type CSSProperties, type InputHTMLAttributes } from "react";

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "style"> & {
  label: string;
  containerStyle?: CSSProperties;
};

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="m3 3 18 18" />
      <path d="M10.6 6.2A11.8 11.8 0 0 1 12 6c7 0 10 6 10 6a16 16 0 0 1-2.1 2.8" />
      <path d="M6.3 6.3A14.8 14.8 0 0 0 2 12s3 6 10 6a10.7 10.7 0 0 0 5.1-1.3" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </svg>
  );
}

export default function PasswordInput({
  label,
  id,
  className,
  containerStyle,
  ...inputProps
}: PasswordInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [visible, setVisible] = useState(false);
  const action = visible ? "Hide" : "Show";

  return (
    <div className="password-field" style={containerStyle}>
      <label className="password-field__label" htmlFor={inputId}>
        {label}
      </label>
      <div className="password-field__control">
        <input
          {...inputProps}
          id={inputId}
          className={["password-field__input", className].filter(Boolean).join(" ")}
          type={visible ? "text" : "password"}
        />
        <button
          type="button"
          className="password-field__toggle"
          aria-label={`${action} ${label.toLowerCase()}`}
          aria-pressed={visible}
          aria-controls={inputId}
          title={`${action} ${label.toLowerCase()}`}
          disabled={inputProps.disabled}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
    </div>
  );
}
