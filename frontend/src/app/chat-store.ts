import { formatDate } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';

import { API_BASE_URL } from './api-base-url';

export type ResponseType = 'answer' | 'clarification' | 'abstention' | 'refusal';

export interface Citation {
  document_id: string;
  document_version: string;
  title: string;
  section: string;
  page_start: number | null;
  page_end: number | null;
  slide: number | null;
  snippet: string;
  status: 'current' | 'superseded';
}

export interface ChatReply {
  response_type: ResponseType;
  message: string;
  citations: Citation[];
}

export type Turn = { role: 'user'; content: string } | { role: 'assistant'; reply: ChatReply };

const HISTORY_TURNS = 6;

@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  readonly asOfDate = signal(new Date());
  readonly turns = signal<Turn[]>([]);
  readonly pending = signal(false);
  readonly error = signal<string | null>(null);

  readonly latestCitations = computed(() => {
    const last = this.turns().at(-1);
    return last?.role === 'assistant' ? last.reply.citations : [];
  });

  ask(question: string): void {
    const content = question.trim();
    if (!content || this.pending()) return;

    this.turns.update((turns) => [...turns, { role: 'user', content }]);
    this.pending.set(true);
    this.error.set(null);

    const body = {
      messages: this.turns()
        .slice(-HISTORY_TURNS)
        .map((turn) =>
          turn.role === 'user'
            ? { role: 'user', content: turn.content }
            : { role: 'assistant', content: turn.reply.message },
        ),
      as_of_date: formatDate(this.asOfDate(), 'yyyy-MM-dd', 'en-US'),
    };

    this.http.post<ChatReply>(`${this.baseUrl}/api/chat`, body).subscribe({
      next: (reply) => {
        this.turns.update((turns) => [...turns, { role: 'assistant', reply }]);
        this.pending.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(err.error?.error?.message ?? 'HR Assist could not be reached.');
        this.pending.set(false);
      },
    });
  }
}
