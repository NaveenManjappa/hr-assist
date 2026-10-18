import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';

import { ChatStore, Citation } from '../chat-store';
import { Composer } from '../composer/composer';

@Component({
  selector: 'app-conversation',
  imports: [Composer],
  templateUrl: './conversation.html',
  styleUrl: './conversation.css',
})
export class Conversation {
  protected readonly chat = inject(ChatStore);
  protected readonly draft = signal('');
  protected readonly suggestions = [
    {
      topic: 'Leave',
      question:
        "How many days of annual leave does a full-time employee with less than 3 years' service receive?",
    },
    { topic: 'Sickness', question: 'When do I need to report that I am off sick?' },
    { topic: 'Expenses', question: 'Can I claim a taxi home after working late?' },
    { topic: 'Hybrid working', question: 'How many days a week can I work from home?' },
  ];

  private readonly body = viewChild.required<ElementRef<HTMLElement>>('body');

  protected ask(question: string): void {
    this.chat.ask(question);
    this.draft.set('');
    queueMicrotask(() => {
      const body = this.body().nativeElement;
      body.scrollTop = body.scrollHeight;
    });
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
