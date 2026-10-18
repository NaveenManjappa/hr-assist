import { DOCUMENT } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';

type ThemePreference = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'hr-assist-theme';

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}

@Component({
  selector: 'app-theme-toggle',
  templateUrl: './theme-toggle.html',
  styleUrl: './theme-toggle.css',
})
export class ThemeToggle {
  protected readonly options: { value: ThemePreference; label: string }[] = [
    { value: 'light', label: 'Light theme' },
    { value: 'dark', label: 'Dark theme' },
    { value: 'system', label: 'Match system theme' },
  ];
  protected readonly preference = signal<ThemePreference>(readStoredPreference());

  constructor() {
    const root = inject(DOCUMENT).documentElement;
    effect(() => {
      const preference = this.preference();
      if (preference === 'system') delete root.dataset['theme'];
      else root.dataset['theme'] = preference;
      try {
        if (preference === 'system') localStorage.removeItem(STORAGE_KEY);
        else localStorage.setItem(STORAGE_KEY, preference);
      } catch {
        // Storage can be unavailable (private mode); the theme still applies for this visit.
      }
    });
  }
}
