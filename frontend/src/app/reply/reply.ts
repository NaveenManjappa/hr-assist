import { Component, computed, input, signal } from '@angular/core';

import { ChatReply, Citation, ResponseType } from '../chat-store';

type Segment = { text: string } | { marker: number };

const PRESENTATION: Record<
  ResponseType,
  { label: string | null; role: string | null; nextStep: string | null }
> = {
  answer: { label: null, role: null, nextStep: null },
  clarification: { label: 'A question for you', role: null, nextStep: null },
  abstention: {
    label: 'Not covered by the policies',
    role: null,
    nextStep:
      "People Operations can help with questions the policies don't cover or that need your own records.",
  },
  refusal: { label: "HR Assist can't help with this", role: 'note', nextStep: null },
};

// The API numbers inline markers to match the order of the Citations, starting at [1].
const MARKER = /\[(\d+)\]/g;

@Component({
  selector: 'app-reply',
  templateUrl: './reply.html',
  styleUrl: './reply.css',
  host: {
    'data-testid': 'reply',
    '[class]': "'reply reply-' + reply().response_type",
    '[attr.data-response-type]': 'reply().response_type',
    '[attr.role]': 'style().role',
  },
})
export class Reply {
  readonly reply = input.required<ChatReply>();
  /** Unique within the page, so each card has an id its markers can link to. */
  readonly idPrefix = input.required<string>();

  protected readonly style = computed(() => PRESENTATION[this.reply().response_type]);
  protected readonly expanded = signal<ReadonlySet<number>>(new Set());

  protected readonly segments = computed<Segment[]>(() => {
    const { message, citations } = this.reply();
    const segments: Segment[] = [];
    let last = 0;
    for (const match of message.matchAll(MARKER)) {
      const marker = Number(match[1]);
      if (marker < 1 || marker > citations.length) continue;
      if (match.index > last) segments.push({ text: message.slice(last, match.index) });
      segments.push({ marker });
      last = match.index + match[0].length;
    }
    if (last < message.length) segments.push({ text: message.slice(last) });
    return segments;
  });

  protected cardId(n: number): string {
    return `${this.idPrefix()}-source-${n}`;
  }

  protected toggle(n: number): void {
    this.expanded.update((open) => {
      const next = new Set(open);
      if (!next.delete(n)) next.add(n);
      return next;
    });
  }

  protected expand(n: number): void {
    this.expanded.update((open) => new Set(open).add(n));
  }

  protected location(citation: Citation): string {
    if (citation.slide !== null) {
      return `slide ${citation.slide}`;
    }
    return citation.page_start === citation.page_end
      ? `p.${citation.page_start}`
      : `pp.${citation.page_start}–${citation.page_end}`;
  }
}
