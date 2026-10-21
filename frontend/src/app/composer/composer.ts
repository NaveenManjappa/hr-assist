import { Component, ElementRef, input, model, output, viewChild } from '@angular/core';

@Component({
  selector: 'app-composer',
  templateUrl: './composer.html',
  host: {
    // Below lg the whole workspace scrolls, so the composer and its logging notice stay pinned in view.
    class:
      'block max-lg:sticky max-lg:bottom-0 max-lg:z-10 max-lg:pt-3 max-lg:bg-[linear-gradient(to_bottom,transparent,var(--surface)_0.75rem)]',
  },
})
export class Composer {
  readonly draft = model('');
  readonly asOfDate = model.required<string>();
  readonly busy = input(false);
  readonly ask = output<string>();

  private readonly question = viewChild.required<ElementRef<HTMLTextAreaElement>>('question');

  focus(): void {
    this.question().nativeElement.focus();
  }

  protected submit(): void {
    if (this.busy() || !this.draft().trim()) return;
    this.ask.emit(this.draft());
  }

  protected changeAsOfDate(value: string): void {
    if (value) this.asOfDate.set(value);
  }

  protected submitOnEnter(event: Event): void {
    const keyboard = event as KeyboardEvent;
    if (keyboard.shiftKey || keyboard.isComposing) return;
    event.preventDefault();
    this.submit();
  }
}
