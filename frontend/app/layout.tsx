export const metadata = {
  title: "MACT Cooperative Manager",
  description: "Cooperative society member, loan, and deduction management",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0 }}>
        {children}
        <footer style={{ textAlign: "center", padding: "1rem", fontSize: "0.75rem", color: "#888" }}>
          © SIDGAKS Tech
        </footer>
      </body>
    </html>
  );
}
