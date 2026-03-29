import { Component, Input, Output, EventEmitter, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-frame-viewer',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="frame-container" #container>
      @if (imageSrc) {
        <img
          #frameImg
          [src]="imageSrc"
          (click)="onClick($event)"
          (load)="onImageLoad()"
          class="frame-image"
          [class.clickable]="interactive"
        />
      } @else {
        <div class="placeholder">
          <p>Upload a video to begin</p>
        </div>
      }
    </div>
  `,
  styles: [`
    .frame-container {
      position: relative;
      background: #1a1a2e;
      border-radius: 8px;
      overflow: hidden;
      min-height: 300px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .frame-image {
      width: 100%;
      height: auto;
      display: block;

      &.clickable {
        cursor: crosshair;
      }
    }

    .placeholder {
      padding: 80px 20px;
      text-align: center;
      color: rgba(255,255,255,0.3);
      font-size: 16px;
    }
  `],
})
export class FrameViewerComponent {
  @Input() imageSrc: string | null = null;
  @Input() interactive = false;
  @Output() frameClick = new EventEmitter<{ x: number; y: number }>();

  @ViewChild('frameImg') frameImg!: ElementRef<HTMLImageElement>;

  private naturalWidth = 0;
  private naturalHeight = 0;

  onImageLoad() {
    const img = this.frameImg?.nativeElement;
    if (img) {
      this.naturalWidth = img.naturalWidth;
      this.naturalHeight = img.naturalHeight;
    }
  }

  onClick(event: MouseEvent) {
    if (!this.interactive || !this.frameImg) return;

    const img = this.frameImg.nativeElement;
    const rect = img.getBoundingClientRect();

    // Map display coords to actual image coords
    const scaleX = this.naturalWidth / rect.width;
    const scaleY = this.naturalHeight / rect.height;

    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;

    this.frameClick.emit({ x, y });
  }
}
