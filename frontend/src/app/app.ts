import { DatePipe } from '@angular/common';
import { Component, inject } from '@angular/core';

import { ChatStore } from './chat-store';
import { ConnectionStatus } from './connection-status/connection-status';
import { Conversation } from './conversation/conversation';
import { EvidencePanel } from './evidence-panel/evidence-panel';
import { ThemeToggle } from './theme-toggle/theme-toggle';

@Component({
  selector: 'app-root',
  imports: [ConnectionStatus, Conversation, DatePipe, EvidencePanel, ThemeToggle],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly asOfDate = inject(ChatStore).asOfDate;
}
