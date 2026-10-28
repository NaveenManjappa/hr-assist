import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from './api-base-url';
import { App } from './app';

const QUESTION =
  "How many days of annual leave does a full-time employee with less than 3 years' service receive?";

const ENTITLEMENT = {
  document_id: 'NDS-HR-LAS-002',
  document_version: 'v1.2',
  title: 'Leave and Absence Standard',
  section: '3.1 Entitlement',
  page_start: 5,
  page_end: 5,
  slide: null,
  snippet: '|Less than 3 years|27|8|35|262.5|',
  status: 'current',
};

const BRIEFING = {
  document_id: 'NDS-HR-PRES-011',
  document_version: 'v1.0',
  title: 'What changes on 1 October 2026: Manager Briefing',
  section: 'Annual leave: what changed',
  page_start: null,
  page_end: null,
  slide: 2,
  snippet: "27 days' annual leave for full-time staff",
  status: 'current',
};

const text = (el: Element) => el.textContent!.replace(/\s+/g, ' ').trim();

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

  it('tells visitors on first load that questions are logged, without blocking a question', async () => {
    const { fixture, root } = await renderPage();

    const notice = root.querySelector<HTMLElement>('[data-testid="logging-notice"]')!;
    expect(text(notice)).toBe(
      "Questions are logged to improve this demo. Don't enter personal information.",
    );

    await ask(root, QUESTION, fixture);

    http.expectOne('http://api.test/api/chat').flush({
      response_type: 'answer',
      message: 'You receive 27 days of annual leave.',
      citations: [ENTITLEMENT],
    });
    await fixture.whenStable();
    expect(root.querySelector('[data-testid="logging-notice"]')).not.toBeNull();
  });

  it('sends the question with the As-Of Date and renders the reply with a source card per Citation', async () => {
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
      citations: [ENTITLEMENT, BRIEFING],
    });
    await fixture.whenStable();

    const reply = root.querySelector<HTMLElement>('[data-testid="reply"]')!;
    expect(reply.dataset['responseType']).toBe('answer');
    expect(reply.textContent).toContain('receives 27 days of annual leave');
    const titles = [...reply.querySelectorAll('[data-testid="source-card"] .card-title')].map(
      (title) => title.textContent!.trim(),
    );
    expect(titles).toEqual([
      'Leave and Absence Standard',
      'What changes on 1 October 2026: Manager Briefing',
    ]);
    expect(root.querySelector('[data-testid="pending"]')).toBeNull();
  });

  it('links each inline marker to its numbered source card, which expands to show the snippet', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);

    http.expectOne('http://api.test/api/chat').flush({
      response_type: 'answer',
      message: 'You receive 27 days of annual leave [1]. Managers were briefed on this [2][1].',
      citations: [ENTITLEMENT, BRIEFING],
    });
    await fixture.whenStable();

    const reply = root.querySelector<HTMLElement>('[data-testid="reply"]')!;
    const markers = [...reply.querySelectorAll<HTMLAnchorElement>('[data-testid="marker"]')];
    expect(markers.map((m) => m.textContent!.trim())).toEqual(['1', '2', '1']);
    expect(reply.querySelector('.reply-message')!.textContent).not.toContain('[');

    const cards = [...reply.querySelectorAll<HTMLElement>('[data-testid="source-card"]')];
    expect(cards).toHaveLength(2);
    expect(markers[1].getAttribute('href')).toBe(`#${cards[1].id}`);
    expect(markers[0].getAttribute('href')).toBe(`#${cards[0].id}`);
    expect(markers[2].getAttribute('href')).toBe(`#${cards[0].id}`);

    expect(text(cards[0])).toContain('1 Leave and Absence Standard');
    expect(text(cards[0])).toContain('NDS-HR-LAS-002 · v1.2 · 3.1 Entitlement · page 5');
    expect(text(cards[1])).toContain(
      'NDS-HR-PRES-011 · v1.0 · Annual leave: what changed · slide 2',
    );

    const toggle = cards[0].querySelector<HTMLButtonElement>('[data-testid="toggle-snippet"]')!;
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(cards[0].querySelector('[data-testid="snippet"]')).toBeNull();

    toggle.click();
    await fixture.whenStable();

    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const cells = cards[0].querySelectorAll('[data-testid="snippet"] td');
    expect([...cells].map(text)).toEqual(['Less than 3 years', '27', '8', '35', '262.5']);
    expect(cards[1].querySelector('[data-testid="snippet"]')).toBeNull();
  });

  it('shows a loading indicator while a reply is pending', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);

    const pending = root.querySelector<HTMLElement>('[data-testid="pending"]')!;
    expect(pending.getAttribute('role')).toBe('status');
    expect(pending.textContent).toContain('Searching the policies');
    expect(root.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);

    http
      .expectOne('http://api.test/api/chat')
      .flush({ response_type: 'answer', message: '27 days.', citations: [] });
    await fixture.whenStable();

    expect(root.querySelector('[data-testid="pending"]')).toBeNull();
  });

  it('shows an error banner when a request fails, and retry resends the same message', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);

    const failed = http.expectOne('http://api.test/api/chat');
    failed.flush(
      { error: { code: 'upstream_unavailable', message: 'The answering service is unavailable.' } },
      { status: 503, statusText: 'Service Unavailable' },
    );
    await fixture.whenStable();

    const banner = root.querySelector<HTMLElement>('[role="alert"]')!;
    expect(banner.textContent).toContain('The answering service is unavailable.');
    expect(root.querySelector('[data-testid="pending"]')).toBeNull();

    banner.querySelector<HTMLButtonElement>('[data-testid="retry"]')!.click();
    await fixture.whenStable();

    const retried = http.expectOne('http://api.test/api/chat');
    expect(retried.request.body).toEqual(failed.request.body);
    expect(root.querySelector('[role="alert"]')).toBeNull();
    expect(root.querySelector('[data-testid="pending"]')).not.toBeNull();

    retried.flush({ response_type: 'answer', message: '27 days.', citations: [] });
    await fixture.whenStable();

    expect(root.querySelectorAll('.question')).toHaveLength(1);
    expect(root.querySelector('[data-testid="reply"]')!.textContent).toContain('27 days.');
  });

  it("shows the backend's message when a chat is rate limited, and offers a retry", async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);

    http.expectOne('http://api.test/api/chat').flush(
      {
        error: {
          code: 'rate_limited',
          message: "You're asking questions too quickly. Please wait a minute and try again.",
          details: [],
          request_id: 'abc123',
        },
      },
      { status: 429, statusText: 'Too Many Requests', headers: { 'Retry-After': '30' } },
    );
    await fixture.whenStable();

    const banner = root.querySelector<HTMLElement>('[role="alert"]')!;
    expect(banner.textContent).toContain(
      "You're asking questions too quickly. Please wait a minute and try again.",
    );
    expect(banner.querySelector('[data-testid="retry"]')).not.toBeNull();
  });

  it('offers example questions on an empty chat, and clicking one sends it', async () => {
    const { fixture, root } = await renderPage();

    const examples = [...root.querySelectorAll<HTMLButtonElement>('[data-testid="example"]')];
    expect(examples.length).toBeGreaterThan(0);
    const question = examples[1].querySelector('.suggestion-text')!.textContent!.trim();

    examples[1].click();
    await fixture.whenStable();

    expect(http.expectOne('http://api.test/api/chat').request.body.messages).toEqual([
      { role: 'user', content: question },
    ]);
    expect(root.querySelector('[data-testid="example"]')).toBeNull();
  });

  it('starts a new conversation from the sidebar, without the earlier turns', async () => {
    const { fixture, root } = await renderPage();
    const newChat = root.querySelector<HTMLButtonElement>('[data-testid="new-chat"]')!;
    expect(newChat.disabled).toBe(true);

    await ask(root, QUESTION, fixture);
    http
      .expectOne('http://api.test/api/chat')
      .flush({ response_type: 'answer', message: '25 days.', citations: [] });
    await fixture.whenStable();

    expect(newChat.disabled).toBe(false);
    expect(root.querySelector('[aria-current="true"]')!.textContent).toContain(QUESTION);
    newChat.click();
    await fixture.whenStable();

    expect(root.querySelector('[data-testid="reply"]')).toBeNull();
    expect(root.querySelector('[data-testid="example"]')).not.toBeNull();
    expect(root.querySelector('[aria-current="true"]')).toBeNull();
    expect(newChat.disabled).toBe(true);

    await ask(root, 'How many days a week can I work from home?', fixture);
    expect(http.expectOne('http://api.test/api/chat').request.body).toEqual({
      messages: [{ role: 'user', content: 'How many days a week can I work from home?' }],
      as_of_date: '2026-10-18',
    });
  });

  it('drops a reply still pending when a new conversation starts', async () => {
    const { fixture, root } = await renderPage();
    await ask(root, QUESTION, fixture);
    const request = http.expectOne('http://api.test/api/chat');

    root.querySelector<HTMLButtonElement>('[data-testid="new-chat"]')!.click();
    await fixture.whenStable();

    expect(request.cancelled).toBe(true);
    expect(root.querySelector('[data-testid="pending"]')).toBeNull();
    expect(root.querySelector('.question')).toBeNull();
    expect(root.querySelector('[data-testid="example"]')).not.toBeNull();
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

    const [superseded, current] = root.querySelectorAll('[data-testid="source-card"]');
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
