/**
 * Reads a Citation snippet: the whole of a chunk's Markdown. Only the subset the parsers emit is
 * understood: headings, **bold**, pipe tables, and bulleted or numbered lists. A <br> inside a
 * table cell is where the PDF wrapped a line, so it reads as a space.
 */

export interface Inline {
  text: string;
  bold: boolean;
}

export type Block =
  | { kind: 'heading'; content: Inline[] }
  | { kind: 'paragraph'; content: Inline[] }
  | { kind: 'list'; ordered: boolean; start: number; items: Inline[][] }
  | { kind: 'table'; head: Inline[][] | null; rows: Inline[][][] };

const HEADING = /^#{1,6}\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;
const TABLE_ROW = /^\s*\|/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

export function parseSnippet(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: 'heading', content: parseInline(heading[1]) });
      i++;
      continue;
    }

    if (TABLE_ROW.test(line)) {
      const rows: Inline[][][] = [];
      let head: Inline[][] | null = null;
      for (; i < lines.length && TABLE_ROW.test(lines[i]); i++) {
        if (TABLE_RULE.test(lines[i])) {
          if (rows.length === 1 && !head) head = rows.pop()!;
        } else {
          rows.push(cells(lines[i]).map(parseInline));
        }
      }
      blocks.push({ kind: 'table', head, rows });
      continue;
    }

    const ordered = NUMBERED.test(line);
    if (ordered || BULLET.test(line)) {
      const pattern = ordered ? NUMBERED : BULLET;
      const start = ordered ? Number(NUMBERED.exec(line)![1]) : 1;
      const items: Inline[][] = [];
      // Items may be separated by blank lines; the list ends at the first other kind of line.
      while (i < lines.length) {
        const item = pattern.exec(lines[i]);
        if (item) {
          items.push(parseInline(item[ordered ? 2 : 1]));
          i++;
        } else if (!lines[i].trim() && pattern.test(lines[i + 1] ?? '')) {
          i++;
        } else {
          break;
        }
      }
      blocks.push({ kind: 'list', ordered, start, items });
      continue;
    }

    const text: string[] = [];
    for (; i < lines.length && lines[i].trim() && !startsBlock(lines[i]); i++) {
      text.push(lines[i].trim());
    }
    blocks.push({ kind: 'paragraph', content: parseInline(text.join(' ')) });
  }

  return blocks;
}

function startsBlock(line: string): boolean {
  return HEADING.test(line) || TABLE_ROW.test(line) || BULLET.test(line) || NUMBERED.test(line);
}

function cells(row: string): string[] {
  const inner = row.trim().replace(/^\|/, '').replace(/\|$/, '');
  return inner.split('|').map((cell) => cell.trim());
}

/** Splits text into plain and **bold** runs. */
export function parseInline(text: string): Inline[] {
  const line = text.replace(/\s*<br\s*\/?>\s*/gi, ' ');
  // A snippet cut inside a bold run leaves a lone "**", which is dropped.
  return line
    .split(/(\*\*[^*]+\*\*)/)
    .map((part) => {
      const bold = part.length > 4 && part.startsWith('**') && part.endsWith('**');
      return { text: bold ? part.slice(2, -2) : part.replaceAll('**', ''), bold };
    })
    .filter((run) => run.text);
}
