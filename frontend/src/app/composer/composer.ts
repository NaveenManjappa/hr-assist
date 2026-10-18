import { Component, ElementRef, model, viewChild } from '@angular/core';

@Component({
  selector: 'app-composer',
  templateUrl: './composer.html',
  styleUrl: './composer.css',
})
export class Composer {
  readonly draft = model('');

  private readonly question = viewChild.required<ElementRef<HTMLTextAreaElement>>('question');

  focus(): void {
    this.question().nativeElement.focus();
  }
}
