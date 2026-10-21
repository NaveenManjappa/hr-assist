import { Component, computed, inject, output } from '@angular/core';

import { ChatStore } from '../chat-store';
import { ConnectionStatus } from '../connection-status/connection-status';
import { Logo } from '../logo/logo';
import { ThemeToggle } from '../theme-toggle/theme-toggle';

@Component({
  selector: 'app-sidebar',
  imports: [ConnectionStatus, Logo, ThemeToggle],
  templateUrl: './sidebar.html',
  host: { class: 'flex h-full flex-col' },
})
export class Sidebar {
  protected readonly chat = inject(ChatStore);
  /** Emitted once the sidebar has done its job, so a drawer holding it can close. */
  readonly done = output();

  /** The open conversation, named after its first question; the list is ready for history. */
  protected readonly current = computed(() => {
    const first = this.chat.turns()[0];
    return first?.role === 'user' ? first.content : null;
  });
  protected readonly started = computed(() => this.chat.turns().length > 0 || !!this.chat.error());

  protected newChat(): void {
    this.chat.reset();
    this.done.emit();
  }
}
