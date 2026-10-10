import { beforeEach, describe, expect, it } from "vitest";
import {
  checkLinkContentType,
  checkResumeText,
  cleanQuery,
  fileKind,
  hasPdfMagic,
  mapLevel,
  rateLimited,
  readCapped,
  resetRateLimits,
  safeHttpUrl,
  validateResumeUrl,
} from "../lib/guards";

const RESUME = "Python engineer who built FastAPI services and trained PyTorch models for two years at a startup.";

describe("resume text", () => {
  it("accepts a normal resume", () => {
    expect(checkResumeText(RESUME)).toEqual({ ok: true, value: RESUME });
  });

  it.each([
    ["", "empty"],
    ["PyTorch and Docker", "too short"],
    ["\u0001\u0002\u0003 ".repeat(40), "doesn't look like text"],
    ["\uFFFD".repeat(100), "doesn't look like text"],
    ["1234 5678 ".repeat(30), "numbers or symbols"],
  ])("rejects %j", (text, message) => {
    const result = checkResumeText(text);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain(message);
  });
});

describe("file types", () => {
  it("classifies by extension and mime", () => {
    expect(fileKind("cv.pdf", "")).toBe("pdf");
    expect(fileKind("cv.txt", "text/plain")).toBe("text");
    expect(fileKind("cv.md", "")).toBe("text");
    expect(fileKind("cv.png", "image/png")).toBeNull();
    expect(fileKind("cv.docx", "application/vnd.openxmlformats")).toBeNull();
  });

  it("recognises PDF magic bytes", () => {
    expect(hasPdfMagic(new TextEncoder().encode("%PDF-1.7 ..."))).toBe(true);
    expect(hasPdfMagic(new TextEncoder().encode("hello world"))).toBe(false);
  });
});

describe("resume links", () => {
  it.each([
    [null, "required"],
    ["", "required"],
    ["not a url", "valid HTTPS"],
    ["http://github.com/a/b", "HTTPS"],
    ["https://user:pw@github.com/a", "HTTPS"],
    ["https://github.com:8443/a", "HTTPS"],
    ["https://localhost/x", "GitHub or Google Drive"],
    ["https://169.254.169.254/latest", "GitHub or Google Drive"],
    ["https://github.com.evil.com/x", "GitHub or Google Drive"],
    [`https://github.com/${"a".repeat(3000)}`, "too long"],
  ])("rejects %j", (value, message) => {
    const result = validateResumeUrl(value);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain(message);
  });

  it("rewrites GitHub blob links to raw", () => {
    const result = validateResumeUrl("https://github.com/me/repo/blob/main/resume.md");
    expect(result.ok && result.value.href).toBe("https://raw.githubusercontent.com/me/repo/main/resume.md");
  });

  it("accepts only plain text content types", () => {
    expect(checkLinkContentType("text/plain; charset=utf-8").ok).toBe(true);
    expect(checkLinkContentType("text/html").ok).toBe(false);
    expect(checkLinkContentType("application/pdf").ok).toBe(false);
    expect(checkLinkContentType("application/json").ok).toBe(false);
    expect(checkLinkContentType(null).ok).toBe(false);
  });

  it("stops reading oversized bodies", async () => {
    const big = new Response("a".repeat(3000));
    const result = await readCapped(big, 1000);
    expect(result.ok).toBe(false);
    const small = await readCapped(new Response("hello"), 1000);
    expect(small.ok && new TextDecoder().decode(small.value)).toBe("hello");
  });
});

describe("job query inputs", () => {
  it("cleans, caps, and defaults the query", () => {
    expect(cleanQuery("  ml    engineer ")).toBe("ml engineer");
    expect(cleanQuery("x".repeat(500))).toHaveLength(100);
    expect(cleanQuery("   ")).toBe("");
    expect(cleanQuery(null)).toBe("");
  });

  it("maps only known levels", () => {
    expect(mapLevel("entry")).toBe("junior");
    expect(mapLevel("Senior")).toBe("senior");
    expect(mapLevel("student")).toBeNull();
    expect(mapLevel("god-tier")).toBeNull();
  });

  it("only allows http(s) apply links", () => {
    expect(safeHttpUrl("https://example.com/apply")).toBe("https://example.com/apply");
    expect(safeHttpUrl("javascript:alert(1)")).toBe("");
    expect(safeHttpUrl("data:text/html,hi")).toBe("");
    expect(safeHttpUrl(undefined)).toBe("");
    expect(safeHttpUrl("nonsense")).toBe("");
  });
});

describe("rate limiting", () => {
  beforeEach(resetRateLimits);

  it("blocks after the limit and recovers after the window", () => {
    const start = 1_000_000;
    for (let index = 0; index < 3; index += 1) expect(rateLimited("ip", 3, 60_000, start)).toBe(false);
    expect(rateLimited("ip", 3, 60_000, start + 1)).toBe(true);
    expect(rateLimited("other", 3, 60_000, start + 1)).toBe(false);
    expect(rateLimited("ip", 3, 60_000, start + 61_000)).toBe(false);
  });
});
