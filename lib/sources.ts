import { safeHttpUrl } from "./guards";

export const USER_AGENT = "RoleRadar/0.3 (+https://github.com/VarunikaN/RoleRadar)";
const AIDEV_URL = "https://aidevboard.com/api/v1/jobs";
const ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api";
const MUSE_URL = "https://www.themuse.com/api/public/jobs";
const TIMEOUT_MS = 10_000;
const MAX_DESCRIPTION_CHARS = 20_000;
const ARBEITNOW_TTL_MS = 3_600_000;

export type SourceJob = {
  id: string;
  title: string;
  company_name: string;
  description: string;
  requirements: string;
  location: string;
  workplace: string;
  experience_level: string;
  tags: string[];
  apply_url: string;
  created_at: string;
  source: string;
};

export class SourceError extends Error {
  constructor(message: string, readonly status = 503) {
    super(message);
  }
}

type Raw = Record<string, unknown>;
const isObject = (value: unknown): value is Raw => typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): string => (typeof value === "string" ? value : typeof value === "number" ? String(value) : "");

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", "#39": "'" };

export function stripHtml(input: unknown): string {
  const value = text(input)
    .replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, " ")
    .replace(/<\/?(?:p|div|br|li|ul|ol|h[1-6]|tr|td|table|section|article)\b[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (whole, name: string) => {
      const lower = name.toLowerCase();
      if (lower in ENTITIES) return ENTITIES[lower];
      const code = lower.startsWith("#x") ? parseInt(lower.slice(2), 16) : lower.startsWith("#") ? parseInt(lower.slice(1), 10) : NaN;
      return Number.isFinite(code) && code > 0 && code < 0x110000 ? String.fromCodePoint(code) : whole;
    });
  return value
    .split(/\r?\n/)
    .map((line) => line.split(/\s+/).filter(Boolean).join(" "))
    .filter(Boolean)
    .join("\n")
    .slice(0, MAX_DESCRIPTION_CHARS);
}

export function queryMatches(job: Pick<SourceJob, "title" | "company_name" | "description" | "tags">, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const haystack = [job.title, job.company_name, job.description, job.tags.join(" ")].join(" ").toLowerCase();
  return words.every((word) => new RegExp(`(?<![\\p{L}\\p{N}_+#])${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "u").test(haystack));
}

async function getJson(url: string, label: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { headers: { "User-Agent": USER_AGENT }, signal: AbortSignal.timeout(TIMEOUT_MS), cache: "no-store" });
  } catch {
    throw new SourceError(`Could not reach ${label}.`);
  }
  if (response.status === 429) throw new SourceError(`${label} is rate limiting requests (HTTP 429). Try again in a minute.`, 429);
  if (response.status === 401 || response.status === 403) throw new SourceError(`${label} rejected the request (HTTP ${response.status}).`);
  if (!response.ok) throw new SourceError(`${label} returned HTTP ${response.status}.`);
  try {
    return await response.json();
  } catch {
    throw new SourceError(`${label} returned an unreadable response.`);
  }
}

async function fetchAiDev(query: string, remote: boolean, level: string | null): Promise<SourceJob[]> {
  const params = new URLSearchParams({ q: query, limit: "30" });
  if (remote) params.set("workplace", "remote");
  if (level) params.set("level", level);
  const payload = await getJson(`${AIDEV_URL}?${params}`, "the AI Dev Jobs API");
  const items = isObject(payload) && Array.isArray(payload.jobs) ? payload.jobs : [];
  return items.filter(isObject).filter((job) => job.id && job.title).map((job) => ({
    id: text(job.id),
    title: text(job.title),
    company_name: text(job.company_name) || "Unknown company",
    description: stripHtml(job.description),
    requirements: stripHtml(job.requirements),
    location: text(job.location),
    workplace: text(job.workplace),
    experience_level: text(job.experience_level),
    tags: Array.isArray(job.tags) ? job.tags.map(String) : [],
    apply_url: safeHttpUrl(job.apply_url),
    created_at: text(job.created_at),
    source: "AI Dev Jobs",
  }));
}

let arbeitnowCache: { at: number; jobs: SourceJob[] } | null = null;

export function clearSourceCache(): void {
  arbeitnowCache = null;
}

async function arbeitnowAll(now = Date.now()): Promise<SourceJob[]> {
  if (arbeitnowCache && now - arbeitnowCache.at < ARBEITNOW_TTL_MS) return arbeitnowCache.jobs;
  const payload = await getJson(ARBEITNOW_URL, "Arbeitnow");
  const items = isObject(payload) && Array.isArray(payload.data) ? payload.data : [];
  const jobs = items.filter(isObject).filter((item) => item.slug && item.title).map((item) => {
    const epoch = Number(item.created_at);
    return {
      id: `arbeitnow-${text(item.slug)}`,
      title: text(item.title),
      company_name: text(item.company_name) || "Unknown company",
      description: stripHtml(item.description),
      requirements: "",
      location: text(item.location),
      workplace: item.remote ? "remote" : "onsite or unspecified",
      experience_level: "",
      tags: [],
      apply_url: safeHttpUrl(item.url),
      created_at: Number.isFinite(epoch) && epoch > 0 ? new Date(epoch * 1000).toISOString() : "",
      source: "Arbeitnow",
    };
  });
  arbeitnowCache = { at: now, jobs };
  return jobs;
}

async function fetchArbeitnow(query: string, remote: boolean): Promise<SourceJob[]> {
  return (await arbeitnowAll()).filter((job) => queryMatches(job, query) && (!remote || job.workplace === "remote"));
}

const MUSE_LEVELS: Record<string, string> = { junior: "Entry Level", mid: "Mid Level", senior: "Senior Level" };
const MUSE_LEVEL_NAMES: Record<string, string> = { "Entry Level": "junior", "Mid Level": "mid", "Senior Level": "senior" };

const MUSE_HINTS: [string[], string][] = [
  [["software", "developer", "programmer", "backend", "frontend", "full stack", "devops", "machine learning", "ml", "ai", "llm"], "Software Engineering"],
  [["data", "analyst", "analytics", "business intelligence", "scientist"], "Data and Analytics"],
  [["design", "ux", "ui", "graphic", "creative"], "Design and UX"],
  [["marketing", "seo", "content", "brand", "social media", "advertising"], "Advertising and Marketing"],
  [["sales", "business development", "account executive"], "Sales"],
  [["account manager", "client success", "customer success"], "Account Management"],
  [["accountant", "accounting", "finance", "financial", "audit", "auditor", "tax", "payroll", "bookkeeper"], "Accounting and Finance"],
  [["hr", "human resources", "recruiter", "recruiting", "talent", "people operations"], "Human Resources and Recruitment"],
  [["nurse", "nursing", "doctor", "physician", "clinical", "medical", "health", "pharmacist", "therapist", "dental"], "Healthcare"],
  [["teacher", "tutor", "professor", "instructor", "education", "curriculum"], "Education"],
  [["product manager", "product management", "product owner"], "Product Management"],
  [["project manager", "program manager", "scrum master"], "Project Management"],
  [["operations", "administrator", "administrative", "coordinator", "office"], "Business Operations"],
  [["customer service", "customer support", "support specialist", "help desk"], "Customer Service"],
  [["legal", "lawyer", "attorney", "paralegal", "counsel", "compliance"], "Legal Services"],
  [["retail", "store", "cashier", "merchandis"], "Retail"],
  [["warehouse", "manufacturing", "production", "assembler"], "Manufacturing and Warehouse"],
  [["logistics", "supply chain", "driver", "dispatcher", "transportation"], "Transportation and Logistics"],
  [["technician", "mechanic", "electrician", "plumber", "hvac", "maintenance", "installer"], "Installation, Maintenance, and Repairs"],
  [["writer", "editor", "journalist", "copywriter"], "Writing and Editing"],
  [["chef", "cook", "restaurant", "hospitality", "hotel", "server", "barista"], "Food and Hospitality Services"],
  [["construction", "contractor"], "Construction"],
  [["it support", "sysadmin", "system administrator", "network", "security analyst", "cybersecurity"], "Computer and IT"],
  [["engineer", "engineering", "scientist", "research"], "Science and Engineering"],
  [["manager", "director", "head of"], "Management"],
];

export function museCategories(query: string): string[] {
  const lowered = ` ${(query.toLowerCase().match(/[a-z0-9+#]+/g) ?? []).join(" ")} `;
  const found: string[] = [];
  for (const [words, category] of MUSE_HINTS) {
    const hit = words.some((word) => lowered.includes(` ${word} `) || (!word.includes(" ") && word.length > 4 && lowered.includes(word)));
    if (hit && !found.includes(category)) found.push(category);
  }
  return found.slice(0, 2);
}

function museJob(item: unknown): SourceJob | null {
  if (!isObject(item) || !item.id || !item.name) return null;
  const names = (Array.isArray(item.locations) ? item.locations : []).filter(isObject).map((place) => text(place.name));
  const remote = names.some((name) => /remote|flexible/i.test(name));
  const levels = (Array.isArray(item.levels) ? item.levels : []).filter(isObject).map((entry) => text(entry.name));
  const level = levels.map((name) => MUSE_LEVEL_NAMES[name]).find(Boolean) ?? "";
  const company = isObject(item.company) ? text(item.company.name) : "";
  const refs = isObject(item.refs) ? text(item.refs.landing_page) : "";
  return {
    id: `muse-${text(item.id)}`,
    title: text(item.name),
    company_name: company || "Unknown company",
    description: stripHtml(item.contents),
    requirements: "",
    location: names.filter(Boolean).join(", "),
    workplace: remote ? "remote" : "onsite or unspecified",
    experience_level: level,
    tags: [],
    apply_url: safeHttpUrl(refs),
    created_at: text(item.publication_date),
    source: "The Muse",
  };
}

async function fetchMuse(query: string, remote: boolean, level: string | null): Promise<SourceJob[]> {
  const categories: (string | null)[] = museCategories(query);
  if (!categories.length) categories.push(null);
  const requests = categories.flatMap((category) => [1, 2].map((page) => ({ category, page })));
  const pages = await Promise.all(
    requests.map(({ category, page }) => {
      const params = new URLSearchParams({ page: String(page) });
      if (category) params.set("category", category);
      if (level && MUSE_LEVELS[level]) params.set("level", MUSE_LEVELS[level]);
      return getJson(`${MUSE_URL}?${params}`, "The Muse");
    }),
  );
  const jobs = new Map<string, SourceJob>();
  for (const payload of pages) {
    const results = isObject(payload) && Array.isArray(payload.results) ? payload.results : [];
    for (const item of results) {
      const job = museJob(item);
      if (job && queryMatches(job, query) && (!remote || job.workplace === "remote")) jobs.set(job.id, job);
    }
  }
  return [...jobs.values()];
}

const ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/in/search/1";

function adzunaConfigured(): boolean {
  return Boolean(process.env.ADZUNA_APP_ID && process.env.ADZUNA_APP_KEY);
}

async function fetchAdzuna(query: string): Promise<SourceJob[]> {
  const params = new URLSearchParams({
    app_id: process.env.ADZUNA_APP_ID ?? "",
    app_key: process.env.ADZUNA_APP_KEY ?? "",
    results_per_page: "30",
  });
  if (query) params.set("what", query);
  const payload = await getJson(`${ADZUNA_URL}?${params}`, "Adzuna");
  const results = isObject(payload) && Array.isArray(payload.results) ? payload.results : [];
  return results.filter(isObject).filter((job) => job.id).map((job) => ({
    id: `adzuna-${text(job.id)}`,
    title: text(job.title) || "Untitled role",
    company_name: (isObject(job.company) && text(job.company.display_name)) || "Unknown company",
    description: stripHtml(job.description),
    requirements: "",
    location: (isObject(job.location) && text(job.location.display_name)) || "India",
    workplace: "onsite or unspecified",
    experience_level: "",
    tags: [],
    apply_url: safeHttpUrl(job.redirect_url),
    created_at: text(job.created),
    source: "Adzuna",
  }));
}

export type Fetched = { jobs: SourceJob[]; warnings: string[] };

export async function fetchAll(query: string, remote: boolean, level: string | null, india = false): Promise<Fetched> {
  const sources = [fetchAiDev(query, remote, level), fetchArbeitnow(query, remote), fetchMuse(query, remote, level)];
  const skipped: string[] = [];
  if (india) {
    if (adzunaConfigured()) sources.push(fetchAdzuna(query));
    else skipped.push("India listings skipped: set ADZUNA_APP_ID and ADZUNA_APP_KEY to enable them.");
  }
  const results = await Promise.allSettled(sources);
  const jobs = new Map<string, SourceJob>();
  const warnings: string[] = [];
  let rateLimited = false;
  for (const result of results) {
    if (result.status === "fulfilled") {
      for (const job of result.value) if (!jobs.has(job.id)) jobs.set(job.id, job);
    } else {
      const reason = result.reason;
      if (reason instanceof SourceError && reason.status === 429) rateLimited = true;
      warnings.push(reason instanceof SourceError ? reason.message : "A job source failed unexpectedly.");
    }
  }
  if (warnings.length === results.length) {
    throw new SourceError(warnings.join(" "), rateLimited ? 429 : 503);
  }
  return { jobs: [...jobs.values()], warnings: [...warnings, ...skipped] };
}
