import type { HomePageModel } from "../hooks/useHomePage";

export default function HomeView({ model }: { model: HomePageModel }) {
  const { user, loading, logout } = model.auth;

  if (loading) return <main style={{ padding: 32 }}>Loading...</main>;

  if (!user) {
    return (
      <main style={{ padding: 32 }}>
        <h1>MACT Cooperative Manager</h1>
        <p>
          <a href="/login">Log in &rarr;</a>
        </p>
      </main>
    );
  }

  const { membersEnabled, loansEnabled, deductionsEnabled } = model.modules;

  return (
    <main style={{ padding: 32 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          maxWidth: 640,
        }}
      >
        <h1>MACT Cooperative Manager</h1>
        <button onClick={logout}>Log out</button>
      </div>
      <p style={{ color: "#555" }}>Signed in as {user.username}.</p>

      {model.settingsError && (
        <p style={{ color: "crimson", fontWeight: 600 }}>
          Unable to load module settings: {model.settingsError}
        </p>
      )}

      {!model.settings && !model.settingsError && <p>Loading modules...</p>}

      {model.settings && (
        <ul>
          {user.role === "member" && (
            <li>
              <a href="/dashboard">Member Dashboard</a>
            </li>
          )}
          {membersEnabled && (
            <li>
              <a href="/members">Members</a>
            </li>
          )}
          {loansEnabled && (
            <li>
              <a href="/loans">Loans</a>
            </li>
          )}
          {user.role === "admin" && loansEnabled && (
            <>
              <li>
                <a href="/admin/loan-applications">Loan Applications (admin review)</a>
              </li>
              <li>
                <a href="/admin/disbursements">Disbursements (admin)</a>
              </li>
              <li>
                <a href="/admin/loan-repayments">Loan Repayments (admin review)</a>
              </li>
            </>
          )}
          {user.role === "admin" && deductionsEnabled && (
            <li>
              <a href="/admin/deductions">Payroll Deductions (admin)</a>
            </li>
          )}
          {user.role === "admin" && (
            <>
              <li>
                <a href="/admin/users">Staff / Admin Users</a>
              </li>
              <li>
                <a href="/admin/offices">Offices</a>
              </li>
              <li>
                <a href="/admin/roles">Roles</a>
              </li>
              <li>
                <a href="/admin/audit">Audit log</a>
              </li>
              <li>
                <a href="/admin/settings">Settings (admin)</a>
              </li>
            </>
          )}
        </ul>
      )}
    </main>
  );
}
