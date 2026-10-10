"use client";

import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Job, cleanSkillList, extractSkills, profileReport, proofPoints, rankJobs, suggestedRole, themesFor } from "../lib/matching";
import { MAX_FILE_BYTES, safeHttpUrl } from "../lib/guards";

const ROLE_PRESETS = [
  "Software Engineer",
  "Data Analyst",
  "Machine Learning Engineer",
  "Accountant",
  "Registered Nurse",
  "Teacher",
  "Sales Executive",
  "Marketing Manager",
  "Graphic Designer",
  "Project Manager",
  "Customer Support Specialist",
  "HR Manager",
  "Operations Manager",
  "Mechanical Engineer",
  "Paralegal",
  "Content Writer",
];

export default function Home() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [resume, setResume] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [link, setLink] = useState("");
  const [target, setTarget] = useState("");
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  const [level, setLevel] = useState("student");
  const [market, setMarket] = useState("India");
  const [remote, setRemote] = useState(false);
  const [manual, setManual] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [status, setStatus] = useState("Upload a PDF, TXT, or Markdown resume to get started.");
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [activeTab, setActiveTab] = useState<"profile" | "roles">("profile");
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const requestId = useRef(0);
  const manualSkills = useMemo(() => cleanSkillList(manual), [manual]);
  const extracted = useMemo(
    () => [...new Set([...extractSkills(resume), ...manualSkills.accepted])],
    [resume, manualSkills],
  );
  const report = useMemo(
    () => ({ headline: suggestedRole(extracted), pillars: themesFor(extracted), proofPoints: proofPoints(resume) }),
    [resume, extracted],
  );
  const ranked = useMemo(() => rankJobs(jobs, extracted), [jobs, extracted]);
  const step = resume ? (jobs.length ? 3 : 2) : 1;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const scan = useCallback(async (next?: { statusPrefix?: string; role?: string }) => {
    const role = (next?.role ?? target).trim();
    if (!role) {
      setError("Enter a target role first, for example Accountant or Data Analyst.");
      return;
    }
    const current = ++requestId.current;
    setIsScanning(true);
    setError("");
    setStatus(next?.statusPrefix ?? "Scanning current role listings and calculating skill alignment...");
    try {
      const res = await fetch(`/api/jobs?q=${encodeURIComponent(role)}&remote=${remote}&level=${level}`);
      const body = await res.json();
      if (current !== requestId.current) return;
      const found: Job[] = Array.isArray(body.jobs) ? body.jobs : [];
      setJobs(found);
      setActiveTab("roles");
      if (body.error) {
        setError(body.error);
        setStatus("Role scan failed.");
      } else if (found.length === 0) {
        setError(`No roles found for '${role}'. That title may not exist in the job feeds. Try a broader title such as analyst, manager or engineer.`);
        setStatus("No roles retrieved.");
      } else {
        const caveat = market === "India" ? " Note: the free sources skew to the US and Europe." : "";
        const warning = Array.isArray(body.warnings) && body.warnings.length ? ` ${body.warnings.join(" ")}` : "";
        setStatus(`${found.length} roles retrieved for '${role}'.${caveat}${warning}`);
      }
    } catch {
      if (current !== requestId.current) return;
      setJobs([]);
      setError("Could not reach the role database. Please try again.");
      setStatus("Role scan failed.");
    } finally {
      if (current === requestId.current) setIsScanning(false);
    }
  }, [target, remote, level, market]);

  function suggestRole(text: string): string {
    const role = target.trim() || profileReport(text).headline;
    if (!target.trim()) setTarget(role);
    return role;
  }

  async function loadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setError("Use a resume smaller than 8 MB.");
      setStatus("Resume upload failed.");
      event.target.value = "";
      return;
    }
    setIsUploading(true);
    setError("");
    setStatus(`Processing ${file.name} and extracting technical skills...`);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/resume", { method: "POST", body: formData });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Upload failed. Please try a text-based PDF, TXT, or Markdown file.");
        setStatus("Resume upload failed.");
        return;
      }
      setResume(body.text);
      setResumeName(body.source ?? file.name);
      setJobs([]);
      const found = extractSkills(body.text).length;
      setStatus(`${body.source ?? file.name} was processed. ${found} skills were identified.`);
      if (found === 0) setError("I read the text but found none of the skills I track. Is this the right document? Add your skills in the sidebar.");
      setActiveTab("profile");
      if (found > 0) void scan({ statusPrefix: "Resume uploaded. Scanning the role database now...", role: suggestRole(body.text) });
    } catch {
      setError("Could not process that file. Please try a text-based PDF, TXT, or Markdown resume.");
      setStatus("Resume upload failed.");
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  }

  async function loadLink() {
    if (!link.trim()) { setError("Enter a public HTTPS resume link first."); return; }
    setIsUploading(true);
    setError("");
    setStatus("Importing the resume from the provided link...");
    try {
      const res = await fetch(`/api/resume?url=${encodeURIComponent(link)}`);
      const body = await res.json();
      if (!res.ok) { setError(body.error ?? "Could not import that resume link."); setStatus("Resume link import failed."); return; }
      setResume(body.text);
      setResumeName(body.source ?? "linked resume");
      setJobs([]);
      const found = extractSkills(body.text).length;
      setStatus(`Resume imported. ${found} skills were identified.`);
      setActiveTab("profile");
      if (found > 0) void scan({ statusPrefix: "Resume imported. Scanning the role database now...", role: suggestRole(body.text) });
      else setError("I read the text but found none of the skills I track. Add your skills in the sidebar.");
    } catch {
      setError("Could not reach that URL.");
      setStatus("Resume link import failed.");
    } finally {
      setIsUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (isUploading) return;
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    const synthetic = { target: { files: e.dataTransfer.files, value: "" } } as unknown as ChangeEvent<HTMLInputElement>;
    void loadFile(synthetic);
  }

  function scoreColor(s: number) {
    if (s >= 60) return "score-high";
    if (s >= 30) return "score-mid";
    return "score-low";
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">RR</span>
          <div>
            <strong>RoleRadar</strong>
            <p>Role matching for any field, grounded in your resume</p>
          </div>
        </div>
        <div className="top-right">
          <div className="status-pill">{isUploading ? "Uploading" : isScanning ? "Scanning" : step === 3 ? "Ready" : "Waiting"}</div>
          <button className="theme-toggle" type="button" onClick={() => setTheme(t => t === "light" ? "dark" : "light")} title="Toggle theme">
            {theme === "light" ? "Dark mode" : "Light mode"}
          </button>
        </div>
      </header>

      <section className="intro">
        <div>
          <p className="kicker">Resume-to-role matching for any field</p>
          <h1>Understand which current roles, in any field, best align with your experience.</h1>
          <p className="lede">
            RoleRadar analyzes your resume, identifies the skills it can verify on the page, and ranks current openings based on
            direct overlap with each job description. Upload a resume once, then refine the target role and rescan at any time.
          </p>
          <p className={`status-text ${error ? "bad" : ""}`}>{error || status}</p>
        </div>
        <ol className="steps">
          <li className={step >= 1 ? "done" : "active"}><b>1</b><span>Upload resume</span></li>
          <li className={step >= 2 ? "done" : step === 2 ? "active" : ""}><b>2</b><span>Review profile</span></li>
          <li className={step >= 3 ? "done" : ""}><b>3</b><span>Match live roles</span></li>
        </ol>
      </section>

      <div className="layout">
        <aside className="sidebar">
          <article className="card">
            <h2>Resume</h2>
            <div
              className={`dropzone${isUploading ? " loading" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <label>
                <input type="file" accept=".pdf,.txt,.md,text/plain,application/pdf,text/markdown" onChange={loadFile} />
                <div className="drop-icon">{isUploading ? "..." : resumeName ? "OK" : "+"}</div>
                <strong>{isUploading ? "Processing resume..." : resumeName ? resumeName : "Drop a resume here or click to upload"}</strong>
                <p>Supported formats: PDF, TXT, and Markdown. Drag and drop is enabled.</p>
              </label>
            </div>
            <div className="link-import">
              <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Or paste a public GitHub or Drive HTTPS link" />
              <button type="button" onClick={loadLink} disabled={isUploading}>Import</button>
            </div>
          </article>

          <article className="card">
            <h2>Target role</h2>
            <div className="role-input-wrap">
              <input
                value={target}
                maxLength={100}
                onChange={(e) => setTarget(e.target.value)}
                onFocus={() => setShowRoleDropdown(true)}
                onBlur={() => setTimeout(() => setShowRoleDropdown(false), 150)}
                placeholder="e.g. Accountant, Data Analyst, Nurse"
              />
              {showRoleDropdown && (
                <div className="role-dropdown">
                  {ROLE_PRESETS.filter((r) => r.toLowerCase().includes(target.toLowerCase()) || target === "").map((r) => (
                    <button key={r} type="button" onMouseDown={() => { setTarget(r); setShowRoleDropdown(false); }}>{r}</button>
                  ))}
                </div>
              )}
            </div>
            <div className="field-row">
              <label>Experience
                <select value={level} onChange={(e) => setLevel(e.target.value)}>
                  <option value="student">Student / Intern</option>
                  <option value="entry">Entry level</option>
                  <option value="mid">Mid level</option>
                  <option value="senior">Senior</option>
                </select>
              </label>
              <label>Market
                <select value={market} onChange={(e) => setMarket(e.target.value)}>
                  <option>India</option>
                  <option>Global</option>
                  <option>Remote worldwide</option>
                </select>
              </label>
            </div>
            <label className="check">
              <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} />
              Remote roles only
            </label>
            <label className="extra-skills">Additional skills not in resume
              <input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="e.g. Excel, Salesforce, Python" />
              {manualSkills.rejected.length > 0 && <span className="dim">Ignored: {manualSkills.rejected.join(", ")}</span>}
            </label>
            <button className="scan-btn" type="button" onClick={() => void scan()} disabled={isScanning || extracted.length === 0}>
              {isScanning ? "Scanning live roles..." : "Rescan live roles"}
            </button>
          </article>

          <article className="card stats-card">
            <h2>Session snapshot</h2>
            <ul>
              <li><span>Skills detected</span><b>{extracted.length}</b></li>
              <li><span>Measurable results</span><b>{report.proofPoints.length}</b></li>
              <li><span>Roles retrieved</span><b>{jobs.length}</b></li>
              <li><span>Roles matched</span><b>{ranked.length}</b></li>
              <li><span>Strong matches (≥50%)</span><b>{ranked.filter(j => j.score >= 50).length}</b></li>
              <li><span>Target</span><b>{target}</b></li>
            </ul>
          </article>
        </aside>

        <main className="content">
          <div className="tabs">
            <button type="button" className={activeTab === "profile" ? "active" : ""} onClick={() => setActiveTab("profile")}>
              Profile & skills
              {extracted.length > 0 && <span className="tab-badge">{extracted.length}</span>}
            </button>
            <button type="button" className={activeTab === "roles" ? "active" : ""} onClick={() => setActiveTab("roles")}>
              Live role matches
              {ranked.length > 0 && <span className="tab-badge">{ranked.length}</span>}
            </button>
          </div>

          {activeTab === "profile" && (
            <div className="tab-content">
              <div className="profile-grid">
                <article className="card">
                  <h3>Suggested role and fields</h3>
                  <p className="positioning">{report.headline || "Not inferred yet"}</p>
                  <div className="pillar-list">
                    {report.pillars.length
                      ? report.pillars.map((p) => <span key={p} className="pillar">{p}</span>)
                      : <p className="dim">Upload a resume to see the fields it points to.</p>}
                  </div>
                </article>
                <article className="card">
                  <h3>Measurable results quoted from your resume</h3>
                  {report.proofPoints.length
                    ? report.proofPoints.map((item) => <p key={item} className="proof-item">{item}</p>)
                    : <p className="dim">No sentence with a measurable result (a %, an amount, a count) was found.</p>}
                </article>
              </div>
              <article className="card">
                <div className="card-title">
                  <h3>Detected skills</h3>
                  <span>{extracted.length} found</span>
                </div>
                <div className="chips">
                  {extracted.length
                    ? extracted.map((s) => <span key={s} className="chip">{s}</span>)
                    : <p className="dim">No recognised skills yet. Upload a resume or add skills in the sidebar.</p>}
                </div>
              </article>
              {resume && (
                <article className="card">
                  <h3>Resume text preview</h3>
                  <pre className="preview">{resume.slice(0, 400)}{resume.length > 400 ? "\n…" : ""}</pre>
                </article>
              )}
            </div>
          )}

          {activeTab === "roles" && (
            <div className="tab-content">
              {ranked.length === 0 ? (
                <div className="empty-state">
                  <strong>{jobs.length ? "No matching roles" : "No role matches yet"}</strong>
                  <p>
                    {jobs.length
                      ? `Found ${jobs.length} roles for '${target}', but none list a skill from your resume. Only skills present on both sides are matched.`
                      : "Upload your resume to automatically scan the role database. You can rescan at any time from the sidebar."}
                  </p>
                </div>
              ) : (
                <div className="jobs">
                  {ranked.map((job) => (
                    <article key={job.id} className={`job${expandedJob === job.id ? " expanded" : ""}`}>
                      <div className={`score-box ${scoreColor(job.score)}`}>
                        <b>{job.score}%</b>
                        <span>match</span>
                      </div>
                      <div className="job-body">
                        <div className="job-header" onClick={() => setExpandedJob(expandedJob === job.id ? null : job.id)}>
                          <div>
                            <h3>{job.title}</h3>
                            <p>{job.company_name || "Unknown company"}{job.source ? ` · via ${job.source}` : ""} · {job.location || "Location not listed"} · {job.workplace || "Workplace not listed"}</p>
                          </div>
                          <span className="expand-icon">{expandedJob === job.id ? "Hide" : "Details"}</span>
                        </div>
                        <div className="skill-rows">
                          <div>
                            <label>Matched skills</label>
                            <div className="chips">
                              {job.matched.length ? job.matched.map((s) => <span key={s} className="chip good">{s}</span>) : <span className="dim">None</span>}
                            </div>
                          </div>
                          <div>
                            <label>Skill gaps</label>
                            <div className="chips">
                              {job.gaps.length ? job.gaps.map((s) => <span key={s} className="chip gap">{s}</span>) : <span className="dim">None detected</span>}
                            </div>
                          </div>
                        </div>
                        {expandedJob === job.id && job.description && (
                          <p className="job-desc">{job.description.slice(0, 500)}{job.description.length > 500 ? "…" : ""}</p>
                        )}
                      </div>
                      {safeHttpUrl(job.apply_url) && (
                        <a href={safeHttpUrl(job.apply_url)} target="_blank" rel="noreferrer" className="apply-btn">Apply</a>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
      <footer className="dim" style={{ textAlign: "center", padding: "16px" }}>
        Listings come from{" "}
        <a href="https://aidevboard.com" target="_blank" rel="noreferrer">AI Dev Jobs</a>,{" "}
        <a href="https://www.arbeitnow.com" target="_blank" rel="noreferrer">Arbeitnow</a> and{" "}
        <a href="https://www.themuse.com" target="_blank" rel="noreferrer">The Muse</a>. Matching is keyword overlap, not machine learning.
      </footer>
    </div>
  );
}
