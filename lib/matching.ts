import data from "./skills.json";

export type Job = {
  id: string;
  title: string;
  company_name?: string;
  location?: string;
  workplace?: string;
  description?: string;
  requirements?: string;
  tags?: string[] | null;
  apply_url?: string;
  created_at?: string;
  source?: string;
};

export type RankedJob = Job & { matched: string[]; gaps: string[]; score: number };

export const SKILLS: readonly string[] = data.skills;
export const ALIASES: Readonly<Record<string, string>> = data.aliases;
export const CATEGORIES: readonly { name: string; role: string; skills: string[] }[] = data.categories;

const CATEGORY_OF = new Map<string, string>(CATEGORIES.flatMap((item) => item.skills.map((skill) => [skill, item.name] as const)));
const ROLE_OF = new Map<string, string>(CATEGORIES.map((item) => [item.name, item.role]));
const CATEGORY_ORDER = new Map<string, number>(CATEGORIES.map((item, index) => [item.name, index]));

const MIN_SKILL_CHARS = 2;
const MAX_SKILL_CHARS = 40;
const SKILL_SHAPE = /^[a-z0-9][a-z0-9+#.\- ]*$/;
const WORD = "\\p{L}\\p{N}_+#";

const URL_PATTERN = /(?:https?:\/\/|www\.)\S+/gi;

function normalize(text: string): string {
  return text.toLowerCase().replace(URL_PATTERN, " ").replace(/[-_/]/g, " ").split(/\s+/).filter(Boolean).join(" ");
}

const patterns = new Map<string, RegExp>();

function pattern(term: string): RegExp {
  let cached = patterns.get(term);
  if (!cached) {
    const escaped = normalize(term).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    cached = new RegExp(`(?:^|[^${WORD}])${escaped}(?![${WORD}])`, "u");
    patterns.set(term, cached);
  }
  return cached;
}

function containsTerm(normalizedText: string, term: string): boolean {
  const wanted = normalize(term);
  if (!wanted || !normalizedText.includes(wanted)) return false;
  return pattern(wanted).test(normalizedText);
}

const TERMS: Map<string, string[]> = (() => {
  const table = new Map<string, string[]>(SKILLS.map((skill) => [skill, [skill]]));
  for (const [alias, target] of Object.entries(ALIASES)) {
    const terms = table.get(target) ?? [target];
    terms.push(alias);
    table.set(target, terms);
  }
  return table;
})();

function termsFor(skill: string): string[] {
  return TERMS.get(skill) ?? [skill];
}

const CANONICAL: Map<string, string> = (() => {
  const table = new Map<string, string>(Object.entries(ALIASES).map(([alias, target]) => [normalize(alias), target]));
  for (const skill of SKILLS) table.set(normalize(skill), skill);
  return table;
})();

export function canonical(term: string): string {
  const cleaned = normalize(term);
  return CANONICAL.get(cleaned) ?? cleaned;
}

function skillsIn(text: string, skills: readonly string[]): string[] {
  const normalized = normalize(text);
  return skills.filter((skill) => termsFor(skill).some((term) => containsTerm(normalized, term)));
}

export function extractSkills(text: string): string[] {
  return skillsIn(text, SKILLS);
}

export function cleanSkillList(raw: string | readonly string[]): { accepted: string[]; rejected: string[] } {
  const items = typeof raw === "string" ? raw.split(",") : raw;
  const accepted: string[] = [];
  const rejected: string[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const cleaned = String(item).trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
    if (!cleaned) continue;
    if (cleaned.length < MIN_SKILL_CHARS) {
      rejected.push(`${cleaned} (too short to match safely)`);
      continue;
    }
    if (cleaned.length > MAX_SKILL_CHARS || !SKILL_SHAPE.test(cleaned) || /^\d+$/.test(cleaned)) {
      rejected.push(`${cleaned.slice(0, MAX_SKILL_CHARS)} (not a skill name)`);
      continue;
    }
    const skill = canonical(cleaned);
    if (!seen.has(skill)) {
      seen.add(skill);
      accepted.push(skill);
    }
  }
  return { accepted, rejected };
}

export function themesFor(skills: readonly string[]): string[] {
  const counts = new Map<string, number>();
  for (const skill of skills) {
    const category = CATEGORY_OF.get(skill);
    if (category) counts.set(category, (counts.get(category) ?? 0) + 1);
  }
  return [...counts.keys()]
    .sort((a, b) => counts.get(b)! - counts.get(a)! || CATEGORY_ORDER.get(a)! - CATEGORY_ORDER.get(b)!)
    .slice(0, 3);
}

export function suggestedRole(skills: readonly string[]): string {
  const [top] = themesFor(skills);
  return top ? (ROLE_OF.get(top) ?? "") : "";
}

const METRIC = /\d+(?:[.,]\d+)?\s?%|[$€£₹]\s?\d|\b\d+(?:[.,]\d+)?\s?(?:x|k|m|million|billion|crore|lakh|users|customers|clients|requests|ms)\b/i;
const BULLET = /^[\s\-*•·▪●–—]+/;

function* sentences(text: string): Generator<string> {
  for (const line of text.split(/[\r\n]+/)) {
    let start = 0;
    for (const match of line.matchAll(/[.!?]+\s+/g)) {
      const end = (match.index ?? 0) + match[0].length;
      yield line.slice(start, end);
      start = end;
    }
    yield line.slice(start);
  }
}

export function proofPoints(text: string): string[] {
  const found: string[] = [];
  for (const sentence of sentences(text)) {
    const cleaned = sentence.replace(BULLET, "").split(/\s+/).filter(Boolean).join(" ");
    const length = Array.from(cleaned).length;
    if (length < 25 || length > 240 || !METRIC.test(cleaned)) continue;
    if (!found.includes(cleaned)) found.push(cleaned);
    if (found.length === 4) break;
  }
  return found;
}

export function profileReport(text: string) {
  const skills = extractSkills(text);
  return { headline: suggestedRole(skills), skills, pillars: themesFor(skills), proofPoints: proofPoints(text) };
}

function jobText(job: Job): string {
  return [job.title ?? "", job.description ?? "", job.requirements ?? "", (job.tags ?? []).map(String).join(" ")].join(" ");
}

function jobSkills(job: Job): Set<string> {
  const tags = (job.tags ?? []).map(String).filter((tag) => normalize(tag)).map(canonical);
  return new Set([...tags, ...extractSkills(jobText(job))]);
}

export function topSkills(jobs: readonly Job[], limit = 8): [string, number][] {
  const counts = new Map<string, number>();
  for (const job of jobs) for (const skill of jobSkills(job)) counts.set(skill, (counts.get(skill) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)).slice(0, limit);
}

export function rankJob(job: Job, skills: readonly string[]): RankedJob | null {
  const candidate = [...new Set(skills.filter((skill) => skill && skill.trim()).map(canonical))];
  if (!candidate.length) return null;
  const matched = skillsIn(jobText(job), candidate).sort();
  if (!matched.length) return null;
  const gaps = [...jobSkills(job)].filter((skill) => !candidate.includes(skill)).sort().slice(0, 6);
  return { ...job, matched, gaps, score: Math.floor((100 * matched.length) / candidate.length + 0.5) };
}

export function rankJobs(jobs: readonly Job[], skills: readonly string[]): RankedJob[] {
  return jobs
    .map((job) => rankJob(job, skills))
    .filter((job): job is RankedJob => job !== null)
    .sort((a, b) => b.score - a.score || (b.created_at ?? "").localeCompare(a.created_at ?? ""));
}
