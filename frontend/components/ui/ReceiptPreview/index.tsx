export default function ReceiptPreview({
  contentType,
  base64,
}: {
  contentType: string;
  base64: string;
}) {
  const src = `data:${contentType};base64,${base64}`;

  if (contentType.startsWith("image/")) {
    return (
      <img
        src={src}
        alt="Payment receipt"
        style={{ maxWidth: "100%", maxHeight: 400, border: "1px solid #ccc" }}
      />
    );
  }

  return (
    <a href={src} download="receipt">
      Download receipt (PDF)
    </a>
  );
}
