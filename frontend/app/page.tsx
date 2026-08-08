import Link from "next/link";

export default function Home() {
  return (
    <main style={{ padding: 32 }}>
      <h1>Cooperative Manager</h1>
      <p>
        <Link href="/members">Go to Members module &rarr;</Link>
      </p>
    </main>
  );
}
