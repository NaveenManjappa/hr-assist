import { Component } from '@angular/core';

/** The HR Assist mark: a person in front of a policy page. Size and colour come from the host. */
@Component({
  selector: 'app-logo',
  template: `
    <svg
      class="size-[60%]"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.9"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M9 8V5a2 2 0 0 1 2-2h5l4 4v12a2 2 0 0 1-2 2h-3" />
      <path d="M16 3v4h4M13 11h4M15 15h2" />
      <circle cx="7.5" cy="13" r="2.5" />
      <path d="M3 21a4.5 4.5 0 0 1 9 0" />
    </svg>
  `,
  host: {
    class: 'grid flex-none place-items-center rounded-lg bg-accent text-accent-contrast',
    'aria-hidden': 'true',
  },
})
export class Logo {}
