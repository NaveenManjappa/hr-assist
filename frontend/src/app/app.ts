import { Component } from '@angular/core';

import { ConnectionStatus } from './connection-status/connection-status';

@Component({
  selector: 'app-root',
  imports: [ConnectionStatus],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
