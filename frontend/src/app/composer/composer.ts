import { Component, ElementRef, input, model, output, viewChild } from '@angular/core';

@Component({
  selector: 'app-composer',
  templateUrl: './composer.html',
  styleUrl: './composer.css',
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
