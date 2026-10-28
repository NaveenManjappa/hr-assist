import { Component, effect, ElementRef, inject, signal, viewChild } from '@angular/core';

import { ChatStore } from '../chat-store';
import { Composer } from '../composer/composer';
import { Logo } from '../logo/logo';
import { Reply } from '../reply/reply';

@Component({
  selector: 'app-conversation',
  imports: [Composer, Logo, Reply],
  templateUrl: './conversation.html',
  host: { class: 'flex min-h-0 flex-1 flex-col' },
})
export class Conversation {
  protected readonly chat = inject(ChatStore);
  protected readonly draft = signal('');
  /** One group per kind of behaviour, so a first-time visitor sees more than plain lookups. */
  protected readonly suggestionGroups = [
    {
      label: 'Answers with citations',
      icon: [
        'M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z',
        'M14 3v5h5',
        'M9 13h6M9 17h4',
      ],
      description: 'every claim links to its source',
      questions: [
        'Will Northstar pay for a taxi home from the station at 22:30 after a client trip?',
        "I'm still on probation. Can I work from Spain for a few days?",
      ],
    },
    {
      label: 'Asks when unclear',
      icon: [
        'M21 12a9 9 0 1 1-3.5-7.1',
        'M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6',
        'M12 17.5h.01',
      ],
      description: 'checks the details before answering',
      questions: ["Will the company pay me while I'm off?", 'Can I claim this expense?'],
    },
    {
      label: 'Knows its limits',
      icon: ['M12 3 5 6v5c0 4.5 3 8.2 7 10 4-1.8 7-5.5 7-10V6z', 'm9 12 2 2 4-4'],
      description: "says what the policies don't cover and declines private questions",
      questions: [
        'How many days of annual leave do I have left?',
        'What salary does the Head of Payroll earn?',
      ],
    },
  ];

  private readonly body = viewChild.required<ElementRef<HTMLElement>>('body');
  private readonly composer = viewChild.required(Composer);

  constructor() {
    // A Clarification expects a reply, so the input is made ready for it.
    effect(() => {
      const last = this.chat.turns().at(-1);
      if (last?.role === 'assistant' && last.reply.response_type === 'clarification') {
        this.composer().focus();
      }
    });
  }

  protected ask(question: string): void {
    this.chat.ask(question);
    this.draft.set('');
    queueMicrotask(() => {
      const body = this.body().nativeElement;
      body.scrollTop = body.scrollHeight;
    });
  }
}
