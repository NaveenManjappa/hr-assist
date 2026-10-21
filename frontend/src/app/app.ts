import { Component, signal } from '@angular/core';

import { Conversation } from './conversation/conversation';
import { Logo } from './logo/logo';
import { Sidebar } from './sidebar/sidebar';

@Component({
  selector: 'app-root',
  imports: [Conversation, Logo, Sidebar],
  templateUrl: './app.html',
  host: {
    class: 'block',
    '(document:keydown.escape)': 'navOpen.set(false)',
  },
})
export class App {
  /** Whether the sidebar drawer is open; below the lg breakpoint the sidebar is a drawer. */
  protected readonly navOpen = signal(false);
}
