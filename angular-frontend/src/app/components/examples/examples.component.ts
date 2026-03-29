import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
@Component({
  selector: 'app-examples',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    @if (examples.length > 0) {
      <div class="examples-section">
        <label>Example Videos</label>
        <div class="examples-row">
          @for (ex of examples; track ex.name) {
            <div class="example-card" (click)="onSelect(ex)" [class.loading]="loadingName === ex.name">
              <img [src]="ex.thumb" class="example-thumb" />
              @if (loadingName === ex.name) {
                <div class="example-overlay">
                  <mat-spinner diameter="24"></mat-spinner>
                </div>
              }
              <span class="example-name">{{ ex.name.replace('.mp4', '') }}</span>
            </div>
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .examples-section {
      display: flex;
      flex-direction: column;
      gap: 6px;

      label {
        color: rgba(255,255,255,0.7);
        font-size: 13px;
        font-weight: 500;
      }
    }

    .examples-row {
      display: flex;
      gap: 8px;
    }

    .example-card {
      position: relative;
      cursor: pointer;
      border-radius: 8px;
      overflow: hidden;
      border: 2px solid transparent;
      transition: border-color 0.2s;
      flex: 1;

      &:hover {
        border-color: #7c3aed;
      }

      &.loading {
        opacity: 0.7;
        pointer-events: none;
      }
    }

    .example-thumb {
      width: 100%;
      height: 80px;
      object-fit: cover;
      display: block;
    }

    .placeholder-thumb {
      background: #2a2a4a;
    }

    .example-overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(0,0,0,0.3);

      mat-icon {
        font-size: 32px;
        width: 32px;
        height: 32px;
        color: rgba(255,255,255,0.8);
      }
    }

    .example-name {
      display: block;
      text-align: center;
      font-size: 11px;
      color: rgba(255,255,255,0.6);
      padding: 2px 0;
      background: rgba(0,0,0,0.5);
    }
  `],
})
export class ExamplesComponent {
  @Input() loadingName: string | null = null;
  @Output() exampleSelected = new EventEmitter<string>();

  examples = [
    { name: 'example1.mp4', thumb: '/examples/example1.jpg' },
    { name: 'example2.mp4', thumb: '/examples/example2.jpg' },
    { name: 'example3.mp4', thumb: '/examples/example3.jpg' },
  ];

  onSelect(ex: { name: string; thumb: string }) {
    if (this.loadingName) return;
    this.exampleSelected.emit(ex.name);
  }
}
