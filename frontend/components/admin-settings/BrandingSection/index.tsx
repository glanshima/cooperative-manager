"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { useBranding } from "@/components/branding/BrandingProvider";
import StatusMessage from "@/components/ui/StatusMessage";
import { deleteLogo, uploadLogo } from "@/lib/api";
import type { SettingsPageModel } from "../hooks/useSettingsPage";

import styles from "./BrandingSection.module.css";

const ALLOWED_LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const ALLOWED_LOGO_LABEL = "PNG, JPEG or WebP";
const MAX_LOGO_BYTES = 1_000_000;
const FEEDBACK_TIMEOUT_MS = 10_000;

type Settings = NonNullable<SettingsPageModel["settings"]>;

interface Feedback {
  tone: "error" | "success";
  text: string;
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () =>
      reject(reader.error ?? new Error("Could not read the selected file."));
    reader.readAsDataURL(file);
  });
}

export default function BrandingSection({
  settings,
  setField,
  readOnly = false,
}: {
  settings: Settings;
  setField: SettingsPageModel["setField"];
  readOnly?: boolean;
}) {
  const { setBranding } = useBranding();
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setFeedback(null), FEEDBACK_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [feedback]);

  // Preview the chosen file before it is uploaded; jsdom has no
  // createObjectURL, so tests fall back to showing the saved logo.
  useEffect(() => {
    if (!pendingFile || typeof URL.createObjectURL !== "function") {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(pendingFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingFile]);

  function applyLogo(saved: Settings, successMessage: string) {
    setField("logo_url", saved.logo_url);
    setBranding({ logo_url: saved.logo_url });
    setFeedback({ tone: "success", text: successMessage });
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFeedback(null);
    const file = event.target.files?.[0] ?? null;

    if (!file) {
      setPendingFile(null);
      return;
    }
    if (!ALLOWED_LOGO_TYPES.includes(file.type)) {
      event.target.value = "";
      setPendingFile(null);
      setFeedback({ tone: "error", text: `Choose a ${ALLOWED_LOGO_LABEL} image.` });
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      event.target.value = "";
      setPendingFile(null);
      setFeedback({ tone: "error", text: "The logo must be 1 MB or smaller." });
      return;
    }
    setPendingFile(file);
  }

  async function handleUpload() {
    if (!pendingFile) return;
    setBusy(true);
    setFeedback(null);
    try {
      const base64 = await readAsBase64(pendingFile);
      const saved = await uploadLogo(pendingFile.type, base64);
      setPendingFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      applyLogo(saved, "Logo updated. It now appears across the app.");
    } catch (e: any) {
      setFeedback({ tone: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove() {
    setBusy(true);
    setFeedback(null);
    try {
      const saved = await deleteLogo();
      applyLogo(saved, "Logo removed. The monogram is shown instead.");
    } catch (e: any) {
      setFeedback({ tone: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  }

  const shownLogo = previewUrl ?? settings.logo_url;

  return (
    <section>
      <h2>Cooperative identity</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
        Shown on the sign-in screens, the admin sidebar and the member dashboard. Save changes to
        apply the name and monogram everywhere.
      </p>
      {readOnly && (
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          You have view-only access to branding. The branding.manage permission is required to
          change it.
        </p>
      )}

      <div className="form-grid" style={{ marginBottom: 16 }}>
        <label>
          Cooperative name
          <input
            required
            disabled={readOnly}
            maxLength={120}
            value={settings.cooperative_name}
            onChange={(e) => setField("cooperative_name", e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
        <label>
          Short name
          <input
            required
            disabled={readOnly}
            maxLength={32}
            value={settings.cooperative_short_name}
            onChange={(e) => setField("cooperative_short_name", e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
        <label>
          Monogram
          <input
            required
            disabled={readOnly}
            maxLength={8}
            value={settings.cooperative_monogram}
            onChange={(e) => setField("cooperative_monogram", e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
      </div>

      <div className={styles.logoRow}>
        {shownLogo ? (
          <img src={shownLogo} alt="Cooperative logo preview" className={styles.logo} />
        ) : (
          <span className={styles.monogram} aria-hidden="true">
            {settings.cooperative_monogram}
          </span>
        )}
        <div className={styles.logoMeta}>
          <strong>{previewUrl ? "New logo preview" : settings.logo_url ? "Current logo" : "No logo uploaded"}</strong>
          <span className={styles.hint}>
            {ALLOWED_LOGO_LABEL}, up to 1 MB. Without a logo the monogram is shown beside the name.
          </span>
        </div>
      </div>

      {!readOnly && (
        <div className={styles.actions}>
          <input
            ref={fileInputRef}
            type="file"
            accept={ALLOWED_LOGO_TYPES.join(",")}
            onChange={handleFileChange}
            aria-label="Choose a logo image"
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!pendingFile || busy}
          >
            {busy ? "Uploading..." : "Upload logo"}
          </button>
          {settings.logo_url && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleRemove}
              disabled={busy}
            >
              Remove logo
            </button>
          )}
        </div>
      )}

      {feedback && (
        <StatusMessage
          tone={feedback.tone}
          onDismiss={() => setFeedback(null)}
          dismissLabel="Dismiss logo message"
        >
          {feedback.text}
        </StatusMessage>
      )}
    </section>
  );
}
