import { DatePipe } from '@angular/common';
import { Component, signal } from '@angular/core';

import { Composer } from './composer/composer';
import { ConnectionStatus } from './connection-status/connection-status';
import { EvidencePanel } from './evidence-panel/evidence-panel';
import { ThemeToggle } from './theme-toggle/theme-toggle';

@Component({
  selector: 'app-root',
  imports: [Composer, ConnectionStatus, DatePipe, EvidencePanel, ThemeToggle],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly asOfDate = new Date();
  protected readonly draft = signal('');
  protected readonly suggestions = [
    { topic: 'Leave', question: 'How many days of annual leave am I entitled to?' },
    { topic: 'Sickness', question: 'When do I need to report that I am off sick?' },
    { topic: 'Expenses', question: 'Can I claim a taxi home after working late?' },
    { topic: 'Hybrid working', question: 'How many days a week can I work from home?' },
  ];
}
