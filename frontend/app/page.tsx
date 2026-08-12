import Link from "next/link";

export default function Home() {
  return (
    <main style={{ padding: 32 }}>
      <h1>MACT Cooperative Ledger</h1>
      <p>
        <Link href="/login">Log in &rarr;</Link>
      </p>
      <p>
        <Link href="/members">Go to Members module &rarr;</Link>
      </p>
      <p>
        <Link href="/loans">Go to Loans module &rarr;</Link>
      </p>
      <p>
        <Link href="/admin/loan-applications">Go to Loan Applications (admin review) &rarr;</Link>
      </p>
      <p>
        <Link href="/admin/settings">Go to Settings (admin) &rarr;</Link>
      </p>
      <p>
        <Link href="/dashboard">Go to Member Dashboard &rarr;</Link>
      </p>
    </main>
  );
}
