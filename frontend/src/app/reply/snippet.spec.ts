import { parseInline, parseSnippet } from './snippet';

describe('Citation snippet', () => {
  it('reads headings, bold text and paragraphs', () => {
    expect(
      parseSnippet('## **Standard carryover rule**\n\nUp to **5 days** may be\ncarried over.'),
    ).toEqual([
      { kind: 'heading', content: [{ text: 'Standard carryover rule', bold: true }] },
      {
        kind: 'paragraph',
        content: [
          { text: 'Up to ', bold: false },
          { text: '5 days', bold: true },
          { text: ' may be carried over.', bold: false },
        ],
      },
    ]);
  });

  it('reads a table with a header row, joining the lines the PDF wrapped inside a cell', () => {
    const [table] = parseSnippet(
      '|**Situation**|**Notice**|\n|---|---|\n|During probation|1 week|\n|After probation|1 month<br>minimum|',
    );

    expect(table).toEqual({
      kind: 'table',
      head: [[{ text: 'Situation', bold: true }], [{ text: 'Notice', bold: true }]],
      rows: [
        [[{ text: 'During probation', bold: false }], [{ text: '1 week', bold: false }]],
        [[{ text: 'After probation', bold: false }], [{ text: '1 month minimum', bold: false }]],
      ],
    });
  });

  it('keeps a table row that the snippet cut off, and a table without a header', () => {
    expect(parseSnippet('|Less than 3 years|27|8|\n|3 to 5 years|28')).toEqual([
      {
        kind: 'table',
        head: null,
        rows: [
          [
            [{ text: 'Less than 3 years', bold: false }],
            [{ text: '27', bold: false }],
            [{ text: '8', bold: false }],
          ],
          [[{ text: '3 to 5 years', bold: false }], [{ text: '28', bold: false }]],
        ],
      },
    ]);
  });

  it('reads bulleted and numbered lists whose items are separated by blank lines', () => {
    const blocks = parseSnippet(
      'Sources:\n\n- **Statutory rights** come first.\n\n- Contract terms.\n\n2. Second.\n\n3. Third.',
    );

    expect(blocks.map((block) => block.kind)).toEqual(['paragraph', 'list', 'list']);
    expect(blocks[1]).toMatchObject({ ordered: false, items: { length: 2 } });
    expect(blocks[2]).toMatchObject({ ordered: true, start: 2, items: { length: 2 } });
  });

  it('drops a bold marker left open where the snippet was cut', () => {
    expect(parseInline('must be taken by **31 Mar')).toEqual([
      { text: 'must be taken by 31 Mar', bold: false },
    ]);
  });
});
