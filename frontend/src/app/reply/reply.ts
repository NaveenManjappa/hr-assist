import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, input, signal } from '@angular/core';

import { ChatReply, Citation, ResponseType } from '../chat-store';
import { parseSnippet } from './snippet';

type Segment = { text: string } | { marker: number };

interface Presentation {
  label: string | null;
  role: string | null;
  nextStep: string | null;
  /** Colour classes for the reply and its label; each type sets its own so none compete. */
  tone: string;
  labelTone: string;
}

// An Answer reads as plain text beside the assistant's mark; the other types sit in a soft panel
// with a label, so the Employee can tell at a glance that this is not a straight answer.
const PANEL = 'rounded-xl border px-4 py-3.5';

const PRESENTATION: Record<ResponseType, Presentation> = {
  answer: { label: null, role: null, nextStep: null, tone: 'pt-0.5', labelTone: '' },
  // A Clarification reads as a question waiting for the Employee's reply.
  clarification: {
    label: 'A question for you',
    role: null,
    nextStep: null,
    tone: `${PANEL} border-accent/25 bg-accent-soft`,
    labelTone: 'bg-surface text-accent ring-accent/25',
  },
  // An Abstention is muted: nothing went wrong, the Corpus just doesn't cover it.
  abstention: {
    label: 'Not covered by the policies',
    role: null,
    nextStep:
      "People Operations can help with questions the policies don't cover or that need your own records.",
    tone: `${PANEL} border-line bg-surface-sunken`,
    labelTone: 'bg-surface text-muted ring-line-strong',
  },
  // A Refusal is a neutral notice, deliberately not error red.
  refusal: {
    label: "HR Assist can't help with this",
    role: 'note',
    nextStep: null,
    tone: `${PANEL} border-line bg-surface-sunken`,
    labelTone: 'bg-surface text-muted ring-line-strong',
  },
};

// The API numbers inline markers to match the order of the Citations, starting at [1].
const MARKER = /\[(\d+)\]/g;

@Component({
  selector: 'app-reply',
  imports: [NgTemplateOutlet],
  templateUrl: './reply.html',
  host: {
    'data-testid': 'reply',
    '[class]': 'hostClass()',
    '[attr.data-response-type]': 'reply().response_type',
    '[attr.role]': 'style().role',
  },
})
export class Reply {
  readonly reply = input.required<ChatReply>();
  /** Unique within the page, so each card has an id its markers can link to. */
  readonly idPrefix = input.required<string>();

  protected readonly style = computed(() => PRESENTATION[this.reply().response_type]);
  protected readonly hostClass = computed(() => `block min-w-0 ${this.style().tone}`);
  protected readonly snippets = computed(() =>
    this.reply().citations.map((citation) => parseSnippet(citation.snippet)),
  );
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
      ? `page ${citation.page_start}`
      : `pages ${citation.page_start}–${citation.page_end}`;
  }
}
