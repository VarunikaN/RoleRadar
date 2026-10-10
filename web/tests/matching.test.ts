import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SKILLS, canonical, cleanSkillList, extractSkills, profileReport, rankJob, rankJobs, topSkills } from "../lib/matching";

type Parity = {
  extract: { name: string; text: string; skills: string[] }[];
  match: {
    name: string;
    skills: string[];
    job: Record<string, unknown>;
    matched: string[];
    score: number;
    missing: string[];
  }[];
  profile: { text: string; headline: string; pillars: string[]; proof_points: string[] }[];
};

const parity: Parity = JSON.parse(readFileSync(join(__dirname, "..", "..", "tests", "parity.json"), "utf-8"));

describe("shared vectors (same file the Python tests read)", () => {
  it.each(parity.extract)("extract: $name", ({ text, skills }) => {
    expect(extractSkills(text)).toEqual(skills);
  });

  it.each(parity.match)("match: $name", ({ skills, job, matched, score, missing }) => {
    const ranked = rankJob({ id: "1", ...job } as never, skills);
    if (matched.length === 0) {
      expect(ranked).toBeNull();
      return;
    }
    expect(ranked?.matched).toEqual(matched);
    expect(ranked?.score).toBe(score);
    expect(ranked?.gaps).toEqual(missing);
  });
});

describe("profile vectors (same file the Python tests read)", () => {
  it.each(parity.profile)("profile: $text", ({ text, headline, pillars, proof_points }) => {
    const report = profileReport(text);
    expect(report.headline).toBe(headline);
    expect(report.pillars).toEqual(pillars);
    expect(report.proofPoints).toEqual(proof_points);
  });

  it("derives gaps and market counts from listing text when there are no tags", () => {
    const job = { id: "1", title: "Accountant", description: "payroll, quickbooks and accounts payable", tags: [] };
    expect(rankJob(job, ["payroll"])?.gaps).toEqual(["accounts payable", "quickbooks"]);
    expect(Object.fromEntries(topSkills([job]))["quickbooks"]).toBe(1);
  });
});

describe("vocabulary", () => {
  it("is byte-identical to the Python vocabulary", () => {
    const python = readFileSync(join(__dirname, "..", "..", "roleradar", "skills.json"), "utf-8");
    const web = readFileSync(join(__dirname, "..", "lib", "skills.json"), "utf-8");
    expect(JSON.parse(web)).toEqual(JSON.parse(python));
    expect(SKILLS).toHaveLength(398);
  });
});

describe("hostile and odd input", () => {
  it("handles null fields without throwing", () => {
    expect(rankJob({ id: "1", title: null as never, tags: null }, ["python"])).toBeNull();
  });

  it("never matches with an empty skill list", () => {
    expect(rankJob({ id: "1", title: "Python dev", tags: ["python"] }, [])).toBeNull();
    expect(rankJob({ id: "1", title: "Python dev" }, ["", "  "])).toBeNull();
  });

  it("drops zero-overlap jobs and sorts best first", () => {
    const jobs = [
      { id: "1", title: "Chef", tags: [] },
      { id: "2", title: "A", description: "python", tags: [] },
      { id: "3", title: "B", description: "python and sql", tags: [] },
    ];
    expect(rankJobs(jobs, ["python", "sql"]).map((job) => job.id)).toEqual(["3", "2"]);
  });

  it("is safe against regex metacharacters in custom skills", () => {
    expect(() => rankJob({ id: "1", title: "x" }, ["(((", "[a-z]+", ".*"])).not.toThrow();
    expect(rankJob({ id: "1", title: "anything at all" }, [".*"])).toBeNull();
  });

  it("treats unicode letters as word characters", () => {
    expect(extractSkills("pythón y sql")).toEqual(["sql"]);
  });

  it("canonicalises aliases and case", () => {
    expect(canonical("Torch")).toBe("pytorch");
    expect(canonical("K8S")).toBe("kubernetes");
    expect(canonical("Some New Tool")).toBe("some new tool");
  });

  it("rejects junk manual skills with reasons", () => {
    const { accepted, rejected } = cleanSkillList("Torch, r, , 12345, " + "x".repeat(80) + ", <script>, PyTorch, c++");
    expect(accepted).toEqual(["pytorch", "c++"]);
    expect(rejected).toHaveLength(4);
  });
});
