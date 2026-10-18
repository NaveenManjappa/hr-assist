import { Component, inject } from '@angular/core';

import { ChatStore } from '../chat-store';

@Component({
  selector: 'app-evidence-panel',
  templateUrl: './evidence-panel.html',
  styleUrl: './evidence-panel.css',
})
export class EvidencePanel {
  protected readonly citations = inject(ChatStore).latestCitations;
}
