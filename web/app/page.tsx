"use client";

import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";

type Job = {
  id: string;
  title: string;
  company_name: string;
  location?: string;
  workplace?: string;
  description?: string;
  requirements?: string;
  tags?: string[];
  apply_url?: string;
};

const ROLE_PRESETS = [
  "Applied AI Engineer",
  "ML Engineer",
  "LLM Engineer",
  "AI Research Engineer",
  "Computer Vision Engineer",
  "NLP Engineer",
  "MLOps Engineer",
  "Data Scientist",
  "AI Product Engineer",
];

const SKILLS = ["python", "c++", "sql", "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy", "llm", "rag", "langchain", "langgraph", "fastapi", "docker", "kubernetes", "aws", "azure", "gcp", "postgresql", "redis", "git", "linux", "transformers", "opencv", "computer vision", "nlp", "machine learning", "deep learning", "cuda", "vllm", "llama.cpp", "quantization", "lora", "peft", "isaac sim", "numba", "streamlit"];
const escape = (v: string) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const extract = (text: string) => SKILLS.filter((s) => new RegExp(`(^|[^\\w+])${escape(s)}($|[^\\w+])`, "i").test(text));

function briefing(text: string, extracted: string[]) {
  const lower = text.toLowerCase();
  const pillarSignals: Array<[string, string[]]> = [
    ["LLM systems", ["quantization", "vllm", "llama.cpp", "lora", "peft"]],
    ["Applied AI products", ["rag", "fastapi", "langchain", "prompt-injection"]],
    ["Vision and robotics", ["computer vision", "isaac sim", "opencv", "segmentation"]],
    ["ML research", ["pytorch", "transformers", "benchmark", "xai"]],
  ];
  const pillars = pillarSignals.filter(([, sig]) => sig.some((s) => lower.includes(s))).map(([name]) => name);
  const proof = [
    ["quantized reasoning model", "Reduced a reasoning model checkpoint from 3.39 GB to 1.74 GB with benchmarked accuracy."],
    ["prompt-injection", "Designed prompt-injection defenses and deterministic validation across AI-agent interactions."],
    ["isaac sim", "Delivered sim-to-real robot manipulation and synthetic-data pipelines in Isaac Sim."],
    ["91.86%", "Achieved 91.86% mIoU on a compact 13.88M-parameter segmentation network."],
    ["100% recall@1", "Built a citation-grounded public-service navigator with 100% Recall@1 on representative queries."],
  ].filter(([sig]) => lower.includes(sig)).map(([, val]) => val as string);
  return { extracted, pillars, proof };
}

function rankJob(job: Job, extracted: string[]) {
  const ev = `${job.title} ${job.description ?? ""} ${job.requirements ?? ""} ${(job.tags ?? []).join(" ")}`.toLowerCase();
  const matched = extracted.filter((s) => ev.includes(s));
  const gaps = (job.tags ?? []).filter((t) => !extracted.includes(t.toLowerCase())).slice(0, 4);
  return { ...job, matched, gaps, score: Math.round((matched.length / Math.max(extracted.length, 1)) * 100) };
}

export default function Home() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [resume, setResume] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [link, setLink] = useState("");
  const [target, setTarget] = useState("Applied AI Engineer");
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
  const extracted = extract(`${resume}\n${manual}`);
  const report = briefing(resume, extracted);
  const ranked = useMemo(() => jobs.map((j) => rankJob(j, extracted)).sort((a, b) => b.score - a.score), [jobs, extracted]);
  const positioning = report.pillars.includes("LLM systems") ? "Applied AI / ML Systems Engineer" : "Applied AI Engineer";
  const step = resume ? (jobs.length ? 3 : 2) : 1;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const scan = useCallback(async (next?: { statusPrefix?: string }) => {
    setIsScanning(true);
    setError("");
    setStatus(next?.statusPrefix ?? "Scanning current role listings and calculating skill alignment...");
    try {
      const res = await fetch(`/api/jobs?q=${encodeURIComponent(target)}&remote=${remote}&level=${level}`);
      const body = await res.json();
      setJobs(body.jobs ?? []);
      const caveat = market === "India" ? " Note: the default source skews US-heavy." : "";
      if (body.error) setError(body.error);
      setStatus(`${body.jobs?.length ?? 0} roles were retrieved and ranked by skill alignment.${caveat}`);
      setActiveTab("roles");
    } catch {
      setJobs([]);
      setError("Could not reach the role database. Please try again.");
      setStatus("Role scan failed.");
    } finally {
      setIsScanning(false);
    }
  }, [target, remote, level, market]);

  async function loadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
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
      setStatus(`${body.source ?? file.name} was processed successfully. ${extract(body.text).length} skills were identified.`);
      setActiveTab("profile");
      void scan({ statusPrefix: "Resume uploaded. Scanning the role database now..." });
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
      setStatus("Resume imported successfully.");
      setActiveTab("profile");
      void scan({ statusPrefix: "Resume imported. Scanning the role database now..." });
    } catch {
      setError("Could not reach that URL.");
      setStatus("Resume link import failed.");
    } finally {
      setIsUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    const synthetic = { target: { files: e.dataTransfer.files, value: "" } } as unknown as ChangeEvent<HTMLInputElement>;
    loadFile(synthetic);
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
            <p>AI role intelligence, grounded in your resume</p>
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
          <p className="kicker">Professional AI role matching</p>
          <h1>Understand which current AI roles best align with your experience.</h1>
          <p className="lede">
            RoleRadar analyzes your resume, identifies verifiable technical skills, and ranks current openings based on
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
                onChange={(e) => setTarget(e.target.value)}
                onFocus={() => setShowRoleDropdown(true)}
                onBlur={() => setTimeout(() => setShowRoleDropdown(false), 150)}
                placeholder="e.g. ML Engineer"
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
              <input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="e.g. PyTorch, FastAPI, LangChain" />
            </label>
            <button className="scan-btn" type="button" onClick={() => void scan()} disabled={isScanning}>
              {isScanning ? "Scanning live roles..." : "Rescan live roles"}
            </button>
          </article>

          <article className="card stats-card">
            <h2>Session snapshot</h2>
            <ul>
              <li><span>Skills detected</span><b>{extracted.length}</b></li>
              <li><span>Proof points</span><b>{report.proof.length}</b></li>
              <li><span>Roles found</span><b>{ranked.length}</b></li>
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
                  <h3>Role positioning</h3>
                  <p className="positioning">{positioning}</p>
                  <div className="pillar-list">
                    {report.pillars.length
                      ? report.pillars.map((p) => <span key={p} className="pillar">{p}</span>)
                      : <p className="dim">Upload a resume to see your positioning themes.</p>}
                  </div>
                </article>
                <article className="card">
                  <h3>Verifiable proof points</h3>
                  {report.proof.length
                    ? report.proof.map((item) => <p key={item} className="proof-item">{item}</p>)
                    : <p className="dim">Add measurable outcomes and benchmarks to your resume to surface proof points here.</p>}
                </article>
              </div>
              <article className="card">
                <div className="card-title">
                  <h3>Detected technical skills</h3>
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
                  <strong>No role matches yet</strong>
                  <p>Upload your resume to automatically scan the role database. You can rescan at any time from the sidebar.</p>
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
                            <p>{job.company_name} · {job.location || "Location not listed"} · {job.workplace || "Workplace not listed"}</p>
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
                              {job.gaps.length ? job.gaps.map((s) => <span key={s} className="chip gap">{s}</span>) : <span className="dim">None tagged</span>}
                            </div>
                          </div>
                        </div>
                        {expandedJob === job.id && job.description && (
                          <p className="job-desc">{job.description.slice(0, 500)}{job.description.length > 500 ? "…" : ""}</p>
                        )}
                      </div>
                      {job.apply_url && (
                        <a href={job.apply_url} target="_blank" rel="noreferrer" className="apply-btn">Apply</a>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
