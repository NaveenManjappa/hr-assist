import { httpResource } from '@angular/common/http';
import { Component, computed, DestroyRef, ElementRef, inject, signal } from '@angular/core';

import { API_BASE_URL } from '../api-base-url';

interface HealthResponse {
  status: 'ok' | 'degraded';
  api: 'up';
  qdrant: 'up' | 'down';
}

type ConnectionState = 'checking' | 'connected' | 'degraded' | 'offline';
type ServiceStatus = 'up' | 'down' | 'unknown';

interface StateView {
  label: string;
  api: ServiceStatus;
  qdrant: ServiceStatus;
}

const STATES: Record<ConnectionState, StateView> = {
  checking: { label: 'Checking…', api: 'unknown', qdrant: 'unknown' },
  connected: { label: 'Connected', api: 'up', qdrant: 'up' },
  degraded: { label: 'Qdrant unreachable', api: 'up', qdrant: 'down' },
  offline: { label: 'API unreachable', api: 'down', qdrant: 'unknown' },
};

const SERVICE_LABELS: Record<ServiceStatus, string> = {
  up: 'Operational',
  down: 'Unreachable',
  unknown: 'Unknown',
};

const POLL_INTERVAL_MS = 30_000;

@Component({
  selector: 'app-connection-status',
  templateUrl: './connection-status.html',
  styleUrl: './connection-status.css',
  host: {
    '(document:click)': 'closeOnOutsideClick($event)',
    '(document:keydown.escape)': 'open.set(false)',
  },
})
export class ConnectionStatus {
  private readonly baseUrl = inject(API_BASE_URL);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly serviceLabels = SERVICE_LABELS;
  protected readonly open = signal(false);
  protected readonly health = httpResource<HealthResponse>(() => `${this.baseUrl}/api/health`);

  protected readonly state = computed<ConnectionState>(() => {
    if (this.health.error()) return 'offline';
    if (!this.health.hasValue()) return 'checking';
    return this.health.value().qdrant === 'up' ? 'connected' : 'degraded';
  });

  protected readonly view = computed(() => STATES[this.state()]);

  constructor() {
    const timer = setInterval(() => this.health.reload(), POLL_INTERVAL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  protected recheck(): void {
    this.health.reload();
  }

  protected closeOnOutsideClick(event: MouseEvent): void {
    if (!this.host.nativeElement.contains(event.target as Node)) this.open.set(false);
  }
}
