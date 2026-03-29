import { Component, Input, Output, EventEmitter, ElementRef, ViewChild, OnChanges, SimpleChanges, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

export interface PointMarker {
  x: number; // image coords
  y: number;
  type: 'positive' | 'negative';
  targetId: number;
  frameIdx: number; // original frame index (before frame_step mapping)
}

@Component({
  selector: 'app-frame-viewer',
  standalone: true,
  imports: [CommonModule, MatProgressSpinnerModule],
  template: `
    <div class="frame-container" #container>
      @if (imageSrc) {
        <div class="image-wrapper">
          <img
            #frameImg
            [src]="imageSrc"
            (click)="onClick($event)"
            (load)="onImageLoad()"
            class="frame-image"
            [class.clickable]="interactive"
            [class.disabled]="loading"
          />
          <canvas
            #markerCanvas
            class="marker-overlay"
            [class.clickable]="interactive"
            (click)="onClick($event)"
            (contextmenu)="onContextMenu($event)"
          ></canvas>
        </div>
        @if (loading) {
          <div class="loading-overlay">
            <mat-spinner diameter="32"></mat-spinner>
          </div>
        }
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

    .image-wrapper {
      position: relative;
      width: 100%;
    }

    .frame-image {
      width: 100%;
      height: auto;
      display: block;

      &.clickable {
        cursor: crosshair;
      }
    }

    .marker-overlay {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;

      &.clickable {
        pointer-events: auto;
        cursor: crosshair;
      }
    }

    .frame-image.disabled {
      pointer-events: none;
      opacity: 0.7;
    }

    .loading-overlay {
      position: absolute;
      top: 12px;
      right: 12px;
      background: rgba(0,0,0,0.6);
      border-radius: 50%;
      padding: 4px;
    }

    .placeholder {
      padding: 80px 20px;
      text-align: center;
      color: rgba(255,255,255,0.3);
      font-size: 16px;
    }
  `],
})
export class FrameViewerComponent implements OnChanges, AfterViewInit {
  @Input() imageSrc: string | null = null;
  @Input() interactive = false;
  @Input() loading = false;
  @Input() markers: PointMarker[] = [];
  @Input() currentFrameIdx = 0;
  @Output() frameClick = new EventEmitter<{ x: number; y: number }>();
  @Output() markerRemove = new EventEmitter<number>(); // emits marker index

  @ViewChild('frameImg') frameImg!: ElementRef<HTMLImageElement>;
  @ViewChild('markerCanvas') markerCanvas!: ElementRef<HTMLCanvasElement>;

  private naturalWidth = 0;
  private naturalHeight = 0;

  // Target colors for different targets
  private targetColors = [
    '#4ade80', '#60a5fa', '#f472b6', '#facc15', '#a78bfa',
    '#34d399', '#f87171', '#38bdf8', '#fb923c', '#c084fc',
  ];

  ngAfterViewInit() {
    this.drawMarkers();
  }

  ngOnChanges(changes: SimpleChanges) {
    if (changes['markers'] || changes['imageSrc'] || changes['currentFrameIdx']) {
      setTimeout(() => this.drawMarkers(), 50);
    }
  }

  onImageLoad() {
    const img = this.frameImg?.nativeElement;
    if (img) {
      this.naturalWidth = img.naturalWidth;
      this.naturalHeight = img.naturalHeight;
    }
    this.drawMarkers();
  }

  onClick(event: MouseEvent) {
    if (!this.interactive || !this.frameImg) return;
    event.preventDefault();
    event.stopPropagation();

    const img = this.frameImg.nativeElement;
    const rect = img.getBoundingClientRect();

    const scaleX = this.naturalWidth / rect.width;
    const scaleY = this.naturalHeight / rect.height;

    const x = (event.clientX - rect.left) * scaleX;
    const y = (event.clientY - rect.top) * scaleY;

    // Right-click on marker → remove it
    if (event.button === 2) {
      const hitIdx = this.findMarkerAt(event.clientX - rect.left, event.clientY - rect.top);
      if (hitIdx >= 0) {
        this.markerRemove.emit(hitIdx);
        return;
      }
    }

    this.frameClick.emit({ x, y });
  }

  onContextMenu(event: MouseEvent) {
    if (!this.interactive || !this.frameImg) return;
    event.preventDefault();

    const img = this.frameImg.nativeElement;
    const rect = img.getBoundingClientRect();

    const hitIdx = this.findMarkerAt(event.clientX - rect.left, event.clientY - rect.top);
    if (hitIdx >= 0) {
      this.markerRemove.emit(hitIdx);
    }
  }

  private findMarkerAt(displayX: number, displayY: number): number {
    if (!this.frameImg || !this.markers.length) return -1;

    const img = this.frameImg.nativeElement;
    const scaleX = img.offsetWidth / this.naturalWidth;
    const scaleY = img.offsetHeight / this.naturalHeight;
    const hitRadius = 15;

    for (let i = this.markers.length - 1; i >= 0; i--) {
      const mx = this.markers[i].x * scaleX;
      const my = this.markers[i].y * scaleY;
      const dist = Math.sqrt((displayX - mx) ** 2 + (displayY - my) ** 2);
      if (dist <= hitRadius) return i;
    }
    return -1;
  }

  private drawMarkers() {
    if (!this.markerCanvas || !this.frameImg || !this.markers.length) {
      if (this.markerCanvas) {
        const canvas = this.markerCanvas.nativeElement;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          canvas.width = canvas.offsetWidth;
          canvas.height = canvas.offsetHeight;
          ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
      }
      return;
    }

    const canvas = this.markerCanvas.nativeElement;
    const img = this.frameImg.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Match canvas size to displayed image
    canvas.width = img.offsetWidth;
    canvas.height = img.offsetHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const scaleX = img.offsetWidth / this.naturalWidth;
    const scaleY = img.offsetHeight / this.naturalHeight;
    const radius = Math.max(6, Math.min(img.offsetWidth, img.offsetHeight) * 0.012);

    for (const marker of this.markers) {
      const isCurrentFrame = marker.frameIdx === this.currentFrameIdx;
      const dx = marker.x * scaleX;
      const dy = marker.y * scaleY;
      const color = this.targetColors[(marker.targetId - 1) % this.targetColors.length];
      const alpha = isCurrentFrame ? 1.0 : 0.3;

      ctx.globalAlpha = alpha;

      // Outer ring
      ctx.beginPath();
      ctx.arc(dx, dy, radius + 2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,0,0,0.5)';
      ctx.fill();

      // Inner circle
      ctx.beginPath();
      ctx.arc(dx, dy, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // + or - symbol
      ctx.strokeStyle = marker.type === 'positive' ? '#000' : '#fff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(dx - radius * 0.5, dy);
      ctx.lineTo(dx + radius * 0.5, dy);
      ctx.stroke();
      if (marker.type === 'positive') {
        ctx.beginPath();
        ctx.moveTo(dx, dy - radius * 0.5);
        ctx.lineTo(dx, dy + radius * 0.5);
        ctx.stroke();
      }

      // Target ID label
      ctx.font = `bold ${Math.round(radius)}px sans-serif`;
      ctx.fillStyle = '#fff';
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 2;
      const label = isCurrentFrame ? `${marker.targetId}` : `T${marker.targetId} F${marker.frameIdx}`;
      ctx.strokeText(label, dx + radius + 3, dy - radius);
      ctx.fillText(label, dx + radius + 3, dy - radius);

      ctx.globalAlpha = 1.0;
    }
  }
}
