import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatSliderModule } from '@angular/material/slider';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-controls',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSliderModule, MatButtonModule, MatButtonToggleModule, MatChipsModule, MatIconModule],
  template: `
    <div class="controls">
      <!-- Frame Rate -->
      <div class="control-group">
        <label>Processing Frame Rate: {{ frameRatePercent }}%</label>
        <div class="framerate-row">
          <mat-slider min="10" max="100" step="5" class="full-width">
            <input matSliderThumb [(ngModel)]="frameRatePercent" (ngModelChange)="onFrameRateChange()" />
          </mat-slider>
          <button mat-stroked-button (click)="applyFrameRate.emit(frameRatePercent)" [disabled]="!hasSession">
            Apply
          </button>
        </div>
        <span class="info-text">{{ frameInfo }}</span>
      </div>

      <!-- Frame Slider -->
      <div class="control-group">
        <label>Frame: {{ currentFrame }} / {{ totalFrames - 1 }}</label>
        <mat-slider [min]="0" [max]="totalFrames - 1" [step]="1" class="full-width" [disabled]="!hasSession">
          <input matSliderThumb [(ngModel)]="currentFrame" (ngModelChange)="frameChange.emit($event)" />
        </mat-slider>
        <span class="info-text">{{ timeText }}</span>
      </div>

      <!-- Point Type -->
      <div class="control-group">
        <label>Annotation Point Type</label>
        <mat-button-toggle-group [value]="pointType" (change)="pointTypeChange.emit($event.value)">
          <mat-button-toggle value="positive">
            <mat-icon>add_circle</mat-icon> Positive
          </mat-button-toggle>
          <mat-button-toggle value="negative">
            <mat-icon>remove_circle</mat-icon> Negative
          </mat-button-toggle>
        </mat-button-toggle-group>
      </div>

      <!-- Targets -->
      <div class="control-group">
        <label>Targets</label>
        <div class="targets-row">
          <mat-chip-set>
            @for (target of targets; track target) {
              <mat-chip>{{ target }}</mat-chip>
            }
          </mat-chip-set>
          <button mat-stroked-button (click)="addTarget.emit()" [disabled]="!hasSession">
            <mat-icon>person_add</mat-icon> Add Target
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .controls {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .control-group {
      display: flex;
      flex-direction: column;
      gap: 4px;

      label {
        color: rgba(255,255,255,0.7);
        font-size: 13px;
        font-weight: 500;
      }
    }

    .framerate-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .targets-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .full-width {
      width: 100%;
    }

    .info-text {
      color: rgba(255,255,255,0.4);
      font-size: 12px;
    }
  `],
})
export class ControlsComponent {
  @Input() hasSession = false;
  @Input() totalFrames = 0;
  @Input() fps = 30;
  @Input() pointType: 'positive' | 'negative' = 'positive';
  @Input() targets: string[] = [];

  @Output() frameChange = new EventEmitter<number>();
  @Output() pointTypeChange = new EventEmitter<string>();
  @Output() addTarget = new EventEmitter<void>();
  @Output() applyFrameRate = new EventEmitter<number>();

  currentFrame = 0;
  frameRatePercent = 100;
  frameInfo = '';

  get timeText(): string {
    if (this.fps <= 0 || this.totalFrames <= 0) return '00:00 / 00:00';
    const curSec = this.currentFrame / this.fps;
    const totalSec = this.totalFrames / this.fps;
    return `${this.formatTime(curSec)} / ${this.formatTime(totalSec)}`;
  }

  onFrameRateChange() {
    const step = Math.max(1, Math.round(100 / this.frameRatePercent));
    const effectiveFrames = Math.ceil(this.totalFrames / step);
    const speedup = (100 / this.frameRatePercent).toFixed(1);
    this.frameInfo = `Frames: ${effectiveFrames} / ${this.totalFrames} (every ${step}) | Speedup: ${speedup}x`;
  }

  private formatTime(sec: number): string {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
}
