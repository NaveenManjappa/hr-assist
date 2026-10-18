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

  it('shows the As-Of Date above the input and sends a changed date with the next question', async () => {
    const { fixture, root } = await renderPage();
    const control = root.querySelector<HTMLInputElement>('input[type="date"]')!;
    expect(root.querySelector('label[for="as-of-date"]')!.textContent).toContain('Answering as of');
    expect(control.value).toBe('2026-10-18');

    control.value = '2026-06-15';
    control.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    await ask(root, 'What was the carryover rule?', fixture);

    expect(http.expectOne('http://api.test/api/chat').request.body.as_of_date).toBe('2026-06-15');
  });

  it('marks a Citation from a superseded source as Superseded', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, 'On 15 June 2026, what was the carryover rule?', fixture);

    http.expectOne('http://api.test/api/chat').flush({
      response_type: 'answer',
      message: 'On 15 June 2026 up to 5 days could be carried over. That rule is superseded.',
      citations: [
        {
          document_id: 'NDS-HR-LV-006',
          document_version: 'v1.0',
          title: 'Leave Policy',
          section: '4.3 Carryover',
          page_start: 3,
          page_end: 3,
          slide: null,
          snippet: 'Up to 5 days of unused leave may be carried over.',
          status: 'superseded',
        },
        {
          document_id: 'NDS-HR-LAS-002',
          document_version: 'v1.2',
          title: 'Leave and Absence Standard',
          section: '3.4 Carryover',
          page_start: 6,
          page_end: 6,
          slide: null,
          snippet: 'Up to 8 days may be carried over.',
          status: 'current',
        },
      ],
    });
    await fixture.whenStable();

    const [superseded, current] = root.querySelectorAll('[data-testid="citation"]');
    expect(superseded.querySelector('[data-testid="superseded"]')!.textContent!.trim()).toBe(
      'Superseded',
    );
    expect(current.querySelector('[data-testid="superseded"]')).toBeNull();
  });

  it('sends only the most recent turns as history', async () => {
    const { fixture, root } = await renderPage();
    for (const n of [1, 2, 3]) {
      await ask(root, `Question ${n}`, fixture);
      http
        .expectOne('http://api.test/api/chat')
        .flush({ response_type: 'answer', message: `Answer ${n}`, citations: [] });
      await fixture.whenStable();
    }

    await ask(root, 'Question 4', fixture);

    expect(http.expectOne('http://api.test/api/chat').request.body.messages).toEqual([
      { role: 'assistant', content: 'Answer 1' },
      { role: 'user', content: 'Question 2' },
      { role: 'assistant', content: 'Answer 2' },
      { role: 'user', content: 'Question 3' },
      { role: 'assistant', content: 'Answer 3' },
      { role: 'user', content: 'Question 4' },
    ]);
  });

  it('styles a Clarification as a question and moves focus back to the input', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, 'Can I take leave next month?', fixture);
    root.querySelector<HTMLButtonElement>('button[type="submit"]')!.focus();

    http.expectOne('http://api.test/api/chat').flush({
      response_type: 'clarification',
      message: 'Which kind of leave do you mean: annual leave, sick leave or another type?',
      citations: [],
    });
    await fixture.whenStable();

    const reply = root.querySelector<HTMLElement>('[data-testid="reply"]')!;
    expect(reply.dataset['responseType']).toBe('clarification');
    expect(reply.querySelector('[data-testid="reply-label"]')!.textContent!.trim()).toBe(
      'A question for you',
    );
    expect(document.activeElement).toBe(root.querySelector('textarea'));
  });

  it('shows an Abstention in a muted style that points to People Operations', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, "What's my leave balance?", fixture);

    http.expectOne('http://api.test/api/chat').flush({
      response_type: 'abstention',
      message: 'HR Assist has no access to your leave balance.',
      citations: [],
    });
    await fixture.whenStable();

    const reply = root.querySelector<HTMLElement>('[data-testid="reply"]')!;
    expect(reply.dataset['responseType']).toBe('abstention');
    expect(reply.querySelector('[data-testid="reply-label"]')!.textContent!.trim()).toBe(
      'Not covered by the policies',
    );
    expect(reply.querySelector('[data-testid="next-step"]')!.textContent).toContain(
      'People Operations',
    );
    expect(document.activeElement).not.toBe(root.querySelector('textarea'));
  });

  it('shows a Refusal as a neutral notice rather than an error', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, 'Why was Tom off sick last week?', fixture);

    http.expectOne('http://api.test/api/chat').flush({
      response_type: 'refusal',
      message:
        "I can't share a colleague's health information. You can ask how sickness absence is reported instead.",
      citations: [],
    });
    await fixture.whenStable();

    const reply = root.querySelector<HTMLElement>('[data-testid="reply"]')!;
    expect(reply.dataset['responseType']).toBe('refusal');
    expect(reply.getAttribute('role')).toBe('note');
    expect(reply.querySelector('[data-testid="reply-label"]')!.textContent!.trim()).toBe(
      "HR Assist can't help with this",
    );
    expect(root.querySelector('[role="alert"]')).toBeNull();
  });

  it('gives an Answer no Response Type label', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);

    http
      .expectOne('http://api.test/api/chat')
      .flush({ response_type: 'answer', message: '27 days.', citations: [] });
    await fixture.whenStable();

    expect(root.querySelector('[data-testid="reply-label"]')).toBeNull();
  });
});
