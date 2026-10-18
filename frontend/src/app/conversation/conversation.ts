import { Component, effect, ElementRef, inject, signal, viewChild } from '@angular/core';

import { ChatStore } from '../chat-store';
import { Composer } from '../composer/composer';
import { Reply } from '../reply/reply';

@Component({
  selector: 'app-conversation',
  imports: [Composer, Reply],
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
