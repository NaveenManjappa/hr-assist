import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from './api-base-url';
import { App } from './app';

const QUESTION =
  "How many days of annual leave does a full-time employee with less than 3 years' service receive?";

describe('Chat page', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers({ now: new Date(2026, 9, 18, 10, 30), toFake: ['Date'] });
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'http://api.test' },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  async function renderPage() {
    const fixture = TestBed.createComponent(App);
    TestBed.tick();
    http.expectOne('http://api.test/api/health').flush({ status: 'ok', api: 'up', qdrant: 'up' });
    await fixture.whenStable();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  async function ask(
    root: HTMLElement,
    question: string,
    fixture: { whenStable(): Promise<unknown> },
  ) {
    const input = root.querySelector<HTMLTextAreaElement>('textarea')!;
    input.value = question;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    root.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
    await fixture.whenStable();
  }

  it('sends the question with the As-Of Date and renders the reply with its Citations', async () => {
    const { fixture, root } = await renderPage();

    await ask(root, QUESTION, fixture);

    const request = http.expectOne('http://api.test/api/chat');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      messages: [{ role: 'user', content: QUESTION }],
      as_of_date: '2026-10-18',
    });
    expect(root.textContent).toContain(QUESTION);
    expect(root.querySelector('[data-testid="pending"]')).not.toBeNull();

    request.flush({
      response_type: 'answer',
      message:
        "A full-time employee with less than 3 years' service receives 27 days of annual leave.",
      citations: [
        {
          document_id: 'NDS-HR-LAS-002',
          document_version: 'v1.2',
          title: 'Leave and Absence Standard',
          section: '3.1 Entitlement',
          page_start: 5,
          page_end: 5,
          slide: null,
          snippet: '|Less than 3 years|27|8|35|262.5|',
          status: 'current',
        },
        {
          document_id: 'NDS-HR-PRES-011',
          document_version: 'v1.0',
          title: 'What changes on 1 October 2026: Manager Briefing',
          section: 'Annual leave: what changed',
          page_start: null,
          page_end: null,
          slide: 2,
          snippet: "27 days' annual leave for full-time staff",
          status: 'current',
        },
      ],
    });
    await fixture.whenStable();

    const reply = root.querySelector<HTMLElement>('[data-testid="reply"]')!;
    expect(reply.dataset['responseType']).toBe('answer');
    expect(reply.textContent).toContain('receives 27 days of annual leave');
    const citations = [...reply.querySelectorAll('[data-testid="citation"]')].map((c) =>
      c.textContent!.replace(/\s+/g, ' ').trim(),
    );
    expect(citations).toEqual([
      'Leave and Absence Standard (NDS-HR-LAS-002 v1.2) · §3.1 Entitlement · p.5',
      'What changes on 1 October 2026: Manager Briefing (NDS-HR-PRES-011 v1.0) · Annual leave: what changed · slide 2',
    ]);
    expect(root.querySelector('[data-testid="pending"]')).toBeNull();
  });

  it('sends the earlier turns as history with a follow-up question', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);
    http
      .expectOne('http://api.test/api/chat')
      .flush({ response_type: 'answer', message: '27 days.', citations: [] });
    await fixture.whenStable();

    await ask(root, 'And after 5 years?', fixture);

    expect(http.expectOne('http://api.test/api/chat').request.body.messages).toEqual([
      { role: 'user', content: QUESTION },
      { role: 'assistant', content: '27 days.' },
      { role: 'user', content: 'And after 5 years?' },
    ]);
  });
});
