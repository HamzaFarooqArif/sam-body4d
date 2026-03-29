import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatProgressBarModule, MatIconModule],
  template: `
    <div class="results">
      <!-- Mask Generation -->
      <div class="result-section">
        <div class="button-row">
          <button
            mat-flat-button
            color="primary"
            (click)="generateMasks.emit()"
            [disabled]="!canGenerate || maskGenerating"
          >
            <mat-icon>layers</mat-icon>
            Mask Generation
          </button>
        </div>

        @if (maskGenerating) {
          <div class="progress-card">
            <div class="progress-label">
              Mask Generation — {{ maskProgress }}%
              <span class="elapsed">{{ maskElapsed }}</span>
            </div>
            <mat-progress-bar mode="determinate" [value]="maskProgress"></mat-progress-bar>
          </div>
        }

        @if (maskVideoUrl) {
          <div class="completed-label">
            Mask Generation completed in {{ maskElapsed }}
          </div>
          <video
            [src]="maskVideoUrl"
            controls
            class="result-video"
          ></video>
        }
      </div>

      <!-- 4D Generation -->
      <div class="result-section">
        <div class="button-row">
          <button
            mat-flat-button
            color="accent"
            (click)="generate4d.emit()"
            [disabled]="!canGenerate || fourDGenerating"
          >
            <mat-icon>view_in_ar</mat-icon>
            4D Generation
          </button>
        </div>

        @if (fourDGenerating) {
          <div class="progress-card">
            <div class="progress-label">
              4D Generation — {{ fourDProgress }}%
              <span class="elapsed">{{ fourDElapsed }}</span>
            </div>
            <mat-progress-bar mode="determinate" [value]="fourDProgress"></mat-progress-bar>
          </div>
        }

        @if (fourDVideoUrl) {
          <div class="completed-label">
            4D Generation completed in {{ fourDElapsed }}
          </div>
          <video
            [src]="fourDVideoUrl"
            controls
            class="result-video"
          ></video>
        }
      </div>
    </div>
  `,
  styles: [`
    .results {
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    .result-section {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .button-row {
      display: flex;
      gap: 8px;

      button {
        flex: 1;
      }
    }

    .progress-card {
      background: #1a1a2e;
      border-radius: 8px;
      padding: 16px;

      .progress-label {
        color: rgba(255,255,255,0.8);
        font-size: 14px;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;

        .elapsed {
          color: rgba(255,255,255,0.4);
        }
      }
    }

    .completed-label {
      color: #4ade80;
      font-size: 13px;
      padding: 4px 0;
    }

    .result-video {
      width: 100%;
      border-radius: 8px;
      background: #000;
    }
  `],
})
export class ResultsComponent {
  @Input() canGenerate = false;
  @Input() maskGenerating = false;
  @Input() maskProgress = 0;
  @Input() maskElapsed = '';
  @Input() maskVideoUrl: string | null = null;
  @Input() fourDGenerating = false;
  @Input() fourDProgress = 0;
  @Input() fourDElapsed = '';
  @Input() fourDVideoUrl: string | null = null;

  @Output() generateMasks = new EventEmitter<void>();
  @Output() generate4d = new EventEmitter<void>();
}
