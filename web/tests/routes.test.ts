import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetRateLimits } from "../lib/guards";

vi.mock("pdf-parse", () => ({
  PDFParse: class {
    static setWorker() {}
    async getText() {
      throw new Error("not a pdf");
    }
    async destroy() {}
  },
}));

const RESUME = "Python engineer who built FastAPI services and trained PyTorch models for two years at a startup.";

async function jobsGet(query: string) {
  const { GET } = await import("../app/api/jobs/route");
  return GET(new NextRequest(`http://localhost/api/jobs?${query}`));
}

function upload(name: string, content: BlobPart, type = "") {
  const form = new FormData();
  form.append("file", new File([content], name, { type }));
  return new NextRequest("http://localhost/api/resume", { method: "POST", body: form });
}

beforeEach(resetRateLimits);
afterEach(() => vi.unstubAllGlobals());

type Handler = (url: string) => Response | Promise<Response>;

function stubSources(handlers: { aidev?: Handler; arbeitnow?: Handler; muse?: Handler }) {
  const empty: Handler = () => Response.json({});
  const mock = vi.fn(async (input: unknown) => {
    const url = String(input);
    if (url.includes("aidevboard")) return (handlers.aidev ?? (() => Response.json({ jobs: [] })))(url);
    if (url.includes("arbeitnow")) return (handlers.arbeitnow ?? (() => Response.json({ data: [] })))(url);
    if (url.includes("themuse")) return (handlers.muse ?? (() => Response.json({ results: [] })))(url);
    return empty(url);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const ARBEITNOW = {
  data: [
    { slug: "n1", title: "Staff Nurse", company_name: "Klinik", description: "<p>patient care &amp; triage</p>", remote: false, tags: [], location: "Berlin", url: "https://example.com/n1", created_at: 1790000000 },
    { slug: "w1", title: "Welder", company_name: "Werk", description: "mig welding", remote: true, tags: [], location: "Hamburg", url: "javascript:alert(1)", created_at: 1790000100 },
  ],
};

describe("GET /api/jobs", () => {
  beforeEach(async () => {
    (await import("../lib/sources")).clearSourceCache();
  });

  it("turns jobs:null from junk queries into an empty list", async () => {
    stubSources({ aidev: () => Response.json({ jobs: null, total: 0 }) });
    const response = await jobsGet("q=asdfghjkl");
    expect(response.status).toBe(200);
    expect((await response.json()).jobs).toEqual([]);
  });

  it("drops malformed jobs and neutralises unsafe apply links", async () => {
    stubSources({
      aidev: () =>
        Response.json({
          jobs: [
            { id: "1", title: "ML Engineer", apply_url: "javascript:alert(1)" },
            { id: "2", title: "Ok", apply_url: "https://example.com/apply" },
            { title: "no id" },
            null,
            "text",
          ],
        }),
    });
    const body = await (await jobsGet("q=ml")).json();
    expect(body.jobs.map((job: { id: string }) => job.id)).toEqual(["1", "2"]);
    expect(body.jobs[0].apply_url).toBe("");
    expect(body.jobs[1].apply_url).toBe("https://example.com/apply");
    expect(body.jobs[0].source).toBe("AI Dev Jobs");
  });

  it("returns non-AI jobs from every source with a source label", async () => {
    stubSources({
      arbeitnow: () => Response.json(ARBEITNOW),
      muse: () => Response.json({ results: [{ id: 9, name: "Registered Nurse", contents: "<b>Patient care</b>", locations: [{ name: "Flexible / Remote" }], levels: [{ name: "Mid Level" }], company: { name: "Acme" }, refs: { landing_page: "https://example.com/9" } }] }),
    });
    const body = await (await jobsGet("q=nurse")).json();
    const bySource = Object.fromEntries(body.jobs.map((job: { source: string; title: string }) => [job.source, job.title]));
    expect(bySource["Arbeitnow"]).toBe("Staff Nurse");
    expect(bySource["The Muse"]).toBe("Registered Nurse");
    expect(body.jobs.find((job: { source: string }) => job.source === "The Muse").workplace).toBe("remote");
    expect(body.warnings).toEqual([]);
  });

  it("sends a cleaned query and a mapped level upstream", async () => {
    const fetchMock = stubSources({});
    await jobsGet(`q=${encodeURIComponent("  ml   engineer  ")}&level=entry&remote=true`);
    const aidev = fetchMock.mock.calls.map((call) => String(call[0])).find((url) => url.includes("aidevboard")) ?? "";
    expect(aidev).toContain("q=ml+engineer");
    expect(aidev).toContain("level=junior");
    expect(aidev).toContain("workplace=remote");
    const muse = fetchMock.mock.calls.map((call) => String(call[0])).filter((url) => url.includes("themuse"));
    expect(muse.every((url) => url.includes("level=Entry+Level"))).toBe(true);
    fetchMock.mockClear();
    await jobsGet("level=student");
    expect(fetchMock.mock.calls.every((call) => !String(call[0]).includes("level="))).toBe(true);
  });

  it("fetches the large Arbeitnow feed once and filters it locally", async () => {
    const fetchMock = stubSources({ arbeitnow: () => Response.json(ARBEITNOW) });
    const first = await (await jobsGet("q=nurse")).json();
    const second = await (await jobsGet("q=welder&remote=true")).json();
    const arbeitnowCalls = fetchMock.mock.calls.filter((call) => String(call[0]).includes("arbeitnow"));
    expect(arbeitnowCalls).toHaveLength(1);
    expect(first.jobs.map((job: { title: string }) => job.title)).toEqual(["Staff Nurse"]);
    expect(second.jobs.map((job: { title: string }) => job.title)).toEqual(["Welder"]);
    expect(second.jobs[0].apply_url).toBe("");
  });

  it("reports a failing source as a warning and still returns the others", async () => {
    stubSources({ muse: () => new Response("x", { status: 500 }), aidev: () => Response.json({ jobs: [{ id: "1", title: "Analyst" }] }) });
    const response = await jobsGet("q=analyst");
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(body.jobs).toHaveLength(1);
    expect(body.warnings).toEqual(["The Muse returned HTTP 500."]);
  });

  it.each([
    [429, 429, "rate limiting"],
    [500, 503, "unavailable"],
  ])("maps every source failing with %i to %i", async (upstream, expected, message) => {
    const fail: Handler = () => new Response("x", { status: upstream });
    stubSources({ aidev: fail, arbeitnow: fail, muse: fail });
    const response = await jobsGet("q=ml");
    expect(response.status).toBe(expected);
    expect((await response.json()).error).toContain(message);
  });

  it("survives network failures and non-JSON bodies", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    expect((await jobsGet("q=ml")).status).toBe(503);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>")));
    expect((await jobsGet("q=ml")).status).toBe(503);
  });

  it("rate limits a noisy client", async () => {
    stubSources({});
    let last = 200;
    for (let index = 0; index < 31; index += 1) last = (await jobsGet("q=ml")).status;
    expect(last).toBe(429);
  });
});

describe("source helpers", () => {
  it("strips tags, scripts and entities", async () => {
    const { stripHtml, museCategories, queryMatches } = await import("../lib/sources");
    expect(stripHtml("<p>Hi&nbsp;<b>there</b></p><script>x</script><li>one</li>")).toBe("Hi there\none");
    expect(stripHtml(null)).toBe("");
    expect(museCategories("Accountant")).toEqual(["Accounting and Finance"]);
    expect(museCategories("zzzzqx")).toEqual([]);
    const listing = { title: "Maintenance Technician", company_name: "", description: "Maintain equipment", tags: [] };
    expect(queryMatches(listing, "ai")).toBe(false);
    expect(queryMatches({ ...listing, title: "Applied AI Engineer" }, "ai engineer")).toBe(true);
    expect(queryMatches(listing, "")).toBe(true);
  });
});

describe("POST /api/resume", () => {
  async function post(request: NextRequest) {
    const { POST } = await import("../app/api/resume/route");
    return POST(request);
  }

  it("accepts a text resume", async () => {
    const response = await post(upload("cv.txt", RESUME, "text/plain"));
    expect(response.status).toBe(200);
    expect((await response.json()).text).toBe(RESUME);
  });

  it.each([
    ["empty file", "cv.txt", "", 400, "empty"],
    ["tiny file", "cv.txt", "PyTorch", 422, "too short"],
    ["image", "cv.png", "x".repeat(200), 415, "Unsupported"],
    ["fake pdf", "cv.pdf", "just some words pretending to be a pdf ".repeat(5), 422, "not a real PDF"],
    ["binary text", "cv.txt", new Uint8Array(Array.from({ length: 600 }, (_, index) => index % 32)), 422, "doesn't look like text"],
  ])("rejects %s", async (_label, name, content, status, message) => {
    const response = await post(upload(name, content as BlobPart));
    expect(response.status).toBe(status);
    expect((await response.json()).error).toContain(message);
  });

  it("rejects a PDF that parses to nothing readable", async () => {
    const response = await post(upload("cv.pdf", "%PDF-1.4 broken", "application/pdf"));
    expect(response.status).toBe(422);
  });

  it("rejects a request with no file", async () => {
    const request = new NextRequest("http://localhost/api/resume", { method: "POST", body: new FormData() });
    expect((await post(request)).status).toBe(400);
  });

  it("rejects bodies that are not multipart", async () => {
    const request = new NextRequest("http://localhost/api/resume", { method: "POST", body: "hello" });
    expect((await post(request)).status).toBe(400);
  });
});

describe("GET /api/resume (links)", () => {
  async function get(url: string) {
    const { GET } = await import("../app/api/resume/route");
    return GET(new NextRequest(`http://localhost/api/resume?url=${encodeURIComponent(url)}`));
  }

  it("blocks private and non-allowlisted hosts before fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const url of ["https://169.254.169.254/latest", "https://localhost/x", "http://github.com/a", "https://evil.com/x"]) {
      expect((await get(url)).status).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns text from an allowed link", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(RESUME, { headers: { "content-type": "text/plain" } })));
    const response = await get("https://raw.githubusercontent.com/me/repo/main/resume.md");
    expect(response.status).toBe(200);
    expect((await response.json()).text).toBe(RESUME);
  });

  it("refuses redirects to hosts outside the allowlist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 302, headers: { location: "https://169.254.169.254/latest" } })),
    );
    expect((await get("https://raw.githubusercontent.com/me/repo/main/resume.md")).status).toBe(502);
  });

  it.each([
    [404, "text/plain", 404],
    [500, "text/plain", 502],
  ])("maps upstream %i", async (status, type, expected) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("x", { status, headers: { "content-type": type } })));
    expect((await get("https://raw.githubusercontent.com/a/b/main/c.md")).status).toBe(expected);
  });

  it("rejects HTML pages with an explanation", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html></html>", { headers: { "content-type": "text/html" } })));
    const response = await get("https://drive.google.com/file/d/abc/view");
    expect(response.status).toBe(422);
    expect((await response.json()).error).toContain("web page");
  });

  it("survives network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    expect((await get("https://raw.githubusercontent.com/a/b/main/c.md")).status).toBe(502);
  });
});
