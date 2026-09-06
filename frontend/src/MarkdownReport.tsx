import { ElementType, Fragment, ReactNode } from "react";

export type MarkdownBlock =
  | { type: "heading"; level: number; content: string }
  | { type: "paragraph"; content: string }
  | { type: "unordered-list"; items: string[] }
  | { type: "ordered-list"; items: string[] }
  | { type: "quote"; content: string }
  | { type: "rule" };

/**
 * Parse the small, deliberately supported Markdown subset used by AI reports.
 * Raw HTML is never interpreted, so model output cannot inject markup/scripts.
 */
export function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];
  let unordered: string[] = [];
  let ordered: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", content: paragraph.join(" ").trim() });
      paragraph = [];
    }
  };
  const flushLists = () => {
    if (unordered.length) {
      blocks.push({ type: "unordered-list", items: unordered });
      unordered = [];
    }
    if (ordered.length) {
      blocks.push({ type: "ordered-list", items: ordered });
      ordered = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushLists();
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushLists();
      blocks.push({ type: "heading", level: heading[1].length, content: heading[2].trim() });
      continue;
    }

    if (/^(?:---+|\*\*\*+|___+)$/.test(trimmed)) {
      flushParagraph();
      flushLists();
      blocks.push({ type: "rule" });
      continue;
    }

    const unorderedItem = trimmed.match(/^[-*+]\s+(.+)$/);
    if (unorderedItem) {
      flushParagraph();
      if (ordered.length) {
        blocks.push({ type: "ordered-list", items: ordered });
        ordered = [];
      }
      unordered.push(unorderedItem[1]);
      continue;
    }

    const orderedItem = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (orderedItem) {
      flushParagraph();
      if (unordered.length) {
        blocks.push({ type: "unordered-list", items: unordered });
        unordered = [];
      }
      ordered.push(orderedItem[1]);
      continue;
    }

    const quote = trimmed.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushLists();
      blocks.push({ type: "quote", content: quote[1] });
      continue;
    }

    flushLists();
    paragraph.push(trimmed);
  }

  flushParagraph();
  flushLists();
  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const tokens = text.split(/(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*]+\*|_[^_]+_)/g).filter(Boolean);
  return tokens.map((token, index) => {
    if ((token.startsWith("**") && token.endsWith("**")) || (token.startsWith("__") && token.endsWith("__"))) {
      return <strong key={index}>{token.slice(2, -2)}</strong>;
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return <code key={index}>{token.slice(1, -1)}</code>;
    }
    if ((token.startsWith("*") && token.endsWith("*")) || (token.startsWith("_") && token.endsWith("_"))) {
      return <em key={index}>{token.slice(1, -1)}</em>;
    }
    return <Fragment key={index}>{token}</Fragment>;
  });
}

export function MarkdownReport({ markdown }: { markdown: string }) {
  const blocks = parseMarkdownBlocks(markdown);

  return (
    <div className="markdown-report" aria-label="AI research report">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "heading": {
            const Heading = `h${Math.min(Math.max(block.level, 2), 4)}` as ElementType;
            return <Heading key={index}>{renderInline(block.content)}</Heading>;
          }
          case "unordered-list":
            return <ul key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)}</ul>;
          case "ordered-list":
            return <ol key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)}</ol>;
          case "quote":
            return <blockquote key={index}>{renderInline(block.content)}</blockquote>;
          case "rule":
            return <hr key={index} />;
          default:
            return <p key={index}>{renderInline(block.content)}</p>;
        }
      })}
    </div>
  );
}
