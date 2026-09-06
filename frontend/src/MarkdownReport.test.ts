import { describe, expect, it } from "vitest";
import { parseMarkdownBlocks } from "./MarkdownReport";

describe("parseMarkdownBlocks", () => {
  it("renders headings, paragraphs, and lists as structured blocks", () => {
    const blocks = parseMarkdownBlocks([
      "## #1. Executive interpretation",
      "",
      "The structure is **broadly bullish**.",
      "",
      "- **Daily** Bullish.",
      "- **H4** Bullish trend.",
      "",
      "1. First point",
      "2. Second point",
    ].join("\n"));

    expect(blocks).toEqual([
      { type: "heading", level: 2, content: "#1. Executive interpretation" },
      { type: "paragraph", content: "The structure is **broadly bullish**." },
      { type: "unordered-list", items: ["**Daily** Bullish.", "**H4** Bullish trend."] },
      { type: "ordered-list", items: ["First point", "Second point"] },
    ]);
  });

  it("never treats raw HTML as a special block", () => {
    const blocks = parseMarkdownBlocks("<script>alert('xss')</script>");
    expect(blocks).toEqual([{ type: "paragraph", content: "<script>alert('xss')</script>" }]);
  });

  it("supports quotes and thematic breaks", () => {
    expect(parseMarkdownBlocks("> Verified deterministic context\n\n---")).toEqual([
      { type: "quote", content: "Verified deterministic context" },
      { type: "rule" },
    ]);
  });
});
