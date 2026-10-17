import { httpResource } from '@angular/common/http';
import { Component, computed, DestroyRef, inject } from '@angular/core';

import { API_BASE_URL } from '../api-base-url';

interface HealthResponse {
  status: 'ok' | 'degraded';
  api: 'up';
  qdrant: 'up' | 'down';
}

type ConnectionState = 'checking' | 'connected' | 'degraded' | 'offline';

const POLL_INTERVAL_MS = 30_000;

const LABELS: Record<ConnectionState, string> = {
  checking: 'Checking…',
  connected: 'Connected',
  degraded: 'Qdrant unreachable',
  offline: 'API unreachable',
};

@Component({
  selector: 'app-connection-status',
  templateUrl: './connection-status.html',
  styleUrl: './connection-status.css',
})
export class ConnectionStatus {
  private readonly baseUrl = inject(API_BASE_URL);

  protected readonly health = httpResource<HealthResponse>(() => `${this.baseUrl}/api/health`);

  protected readonly state = computed<ConnectionState>(() => {
    if (this.health.error()) return 'offline';
    if (!this.health.hasValue()) return 'checking';
    return this.health.value().qdrant === 'up' ? 'connected' : 'degraded';
  });

  protected readonly label = computed(() => LABELS[this.state()]);
  protected readonly apiUp = computed(() => this.health.hasValue());
  protected readonly qdrantUp = computed(
    () => this.health.hasValue() && this.health.value().qdrant === 'up',
  );

  constructor() {
    const timer = setInterval(() => this.health.reload(), POLL_INTERVAL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  protected recheck(): void {
    this.health.reload();
  }
}
