import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { User, UserType } from "../lib/types";

const USER_TYPES: UserType[] = [
  "Organisation",
  "Government Agency",
  "Influencer",
  "Researcher",
  "Journalist",
  "Individual",
];

const TYPE_DESC: Record<UserType, string> = {
  Organisation: "Corporate comms, SOC and security teams",
  "Government Agency": "Ministries, CERTs and public bodies",
  Influencer: "Creators distributing public-facing content",
  Researcher: "Analysts publishing findings and reports",
  Journalist: "Media covering incidents and policy",
  Individual: "Personal and ad-hoc use",
};

export default function Auth() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [organisation, setOrganisation] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [userType, setUserType] = useState<UserType>("Organisation");
  const [error, setError] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password.trim()) return setError("Email and password are required.");
    if (mode === "signup" && !name.trim()) return setError("Name is required.");
    const user: User = {
      name: mode === "signup" ? name.trim() : email.split("@")[0],
      email: email.trim(),
      userType,
      organisation: organisation.trim() || undefined,
    };
    localStorage.setItem("tx.user", JSON.stringify(user));
    navigate("/", { replace: true });
  }

  return (
    <div className="auth">
      <aside className="auth-brand">
        <div className="logo-mark">⌁</div>
        <h1>Transmute</h1>
        <p className="auth-tagline">
          One source. Every deliverable. Transform reports, advisories and raw intelligence into
          publication-ready artefacts.
        </p>
        <ul className="auth-points">
          <li>Multi-format source ingestion</li>
          <li>9 output types from a single run</li>
          <li>Editable markdown deliverables</li>
        </ul>
      </aside>

      <main className="auth-panel">
        <form className="auth-form" onSubmit={submit}>
          <div className="segmented">
            <button
              type="button"
              className={mode === "login" ? "on" : ""}
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "signup" ? "on" : ""}
              onClick={() => setMode("signup")}
            >
              Create account
            </button>
          </div>

          {mode === "signup" && (
            <>
              <label>
                Full name
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Aditi Sharma"
                  autoFocus
                />
              </label>
              <label>
                Organisation <span className="opt">(optional)</span>
                <input
                  value={organisation}
                  onChange={(e) => setOrganisation(e.target.value)}
                  placeholder="Acme Corp / CERT-In"
                />
              </label>
            </>
          )}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@organisation.gov"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>

          {mode === "signup" && (
            <fieldset className="user-types">
              <legend>Account type</legend>
              <div className="type-grid">
                {USER_TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={userType === t ? "on" : ""}
                    onClick={() => setUserType(t)}
                    title={TYPE_DESC[t]}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <p className="type-desc">{TYPE_DESC[userType]}</p>
            </fieldset>
          )}

          {error && <p className="form-error">{error}</p>}

          <button className="primary" type="submit">
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
          <p className="auth-note">
            Demo build — credentials are stored locally, no server round-trip yet.
          </p>
        </form>
      </main>
    </div>
  );
}
