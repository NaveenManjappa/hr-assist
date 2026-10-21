import { formatDate } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { Subscription } from 'rxjs';

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

interface ChatRequest {
  messages: { role: 'user' | 'assistant'; content: string }[];
  as_of_date: string;
}

const HISTORY_TURNS = 6;

@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  readonly asOfDate = signal(formatDate(new Date(), 'yyyy-MM-dd', 'en-US'));
  readonly turns = signal<Turn[]>([]);
  readonly pending = signal(false);
  readonly error = signal<string | null>(null);

  private failedRequest: ChatRequest | null = null;
  private inFlight: Subscription | null = null;

  ask(question: string): void {
    const content = question.trim();
    if (!content || this.pending()) return;

    this.turns.update((turns) => [...turns, { role: 'user', content }]);
    this.send({
      messages: this.turns()
        .slice(-HISTORY_TURNS)
        .map((turn) =>
          turn.role === 'user'
            ? { role: 'user', content: turn.content }
            : { role: 'assistant', content: turn.reply.message },
        ),
      as_of_date: this.asOfDate(),
    });
  }

  /** Resends the request that failed, so the Employee doesn't have to retype it. */
  retry(): void {
    if (this.failedRequest && !this.pending()) this.send(this.failedRequest);
  }

  /** Starts a new conversation. A reply still on its way is dropped; the As-Of Date is kept. */
  reset(): void {
    this.inFlight?.unsubscribe();
    this.inFlight = null;
    this.failedRequest = null;
    this.turns.set([]);
    this.pending.set(false);
    this.error.set(null);
  }

  private send(body: ChatRequest): void {
    this.pending.set(true);
    this.error.set(null);
    this.failedRequest = null;

    this.inFlight = this.http.post<ChatReply>(`${this.baseUrl}/api/chat`, body).subscribe({
      next: (reply) => {
        this.turns.update((turns) => [...turns, { role: 'assistant', reply }]);
        this.pending.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.failedRequest = body;
        this.error.set(err.error?.error?.message ?? 'HR Assist could not be reached.');
        this.pending.set(false);
      },
    });
  }
}
