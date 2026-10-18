import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
  TestRequest,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from './api-base-url';
import { App } from './app';

describe('App shell', () => {
  let http: HttpTestingController;

  beforeEach(() => {
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

  afterEach(() => http.verify());

  async function renderWithHealth(respond: (req: TestRequest) => void) {
    const fixture = TestBed.createComponent(App);
    TestBed.tick();
    respond(http.expectOne('http://api.test/api/health'));
    await fixture.whenStable();
    const root = fixture.nativeElement as HTMLElement;
    return root.querySelector<HTMLElement>('[data-testid="connection-status"]')!;
  }

  it('shows connected when the API is up and Qdrant is reachable', async () => {
    const status = await renderWithHealth((req) =>
      req.flush({ status: 'ok', api: 'up', qdrant: 'up' }),
    );

    expect(status.dataset['state']).toBe('connected');
    expect(status.textContent).toContain('Connected');
  });

  it('shows degraded when the API is up but Qdrant is unreachable', async () => {
    const status = await renderWithHealth((req) =>
      req.flush({ status: 'degraded', api: 'up', qdrant: 'down' }),
    );

    expect(status.dataset['state']).toBe('degraded');
    expect(status.textContent).toContain('Qdrant unreachable');
  });

  it('shows offline when the API cannot be reached', async () => {
    const status = await renderWithHealth((req) =>
      req.error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' }),
    );

    expect(status.dataset['state']).toBe('offline');
    expect(status.textContent).toContain('API unreachable');
  });
});
