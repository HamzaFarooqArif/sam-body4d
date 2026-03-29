import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-video-upload',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div
      class="upload-area"
      [class.dragover]="isDragover"
      (dragover)="onDragOver($event)"
      (dragleave)="isDragover = false"
      (drop)="onDrop($event)"
      (click)="fileInput.click()"
    >
      @if (uploading) {
        <mat-spinner diameter="40"></mat-spinner>
        <p>Uploading video to server...</p>
      } @else {
        <mat-icon class="upload-icon">cloud_upload</mat-icon>
        <p>Drop video here or click to upload</p>
        <span class="hint">MP4 files only</span>
      }
    </div>
    <input
      #fileInput
      type="file"
      accept="video/mp4,.mp4"
      hidden
      (change)="onFileSelected($event)"
    />
  `,
  styles: [`
    .upload-area {
      border: 2px dashed rgba(255,255,255,0.2);
      border-radius: 12px;
      padding: 40px;
      text-align: center;
      cursor: pointer;
      transition: all 0.3s;
      background: rgba(255,255,255,0.02);

      &:hover, &.dragover {
        border-color: #7c3aed;
        background: rgba(124, 58, 237, 0.05);
      }

      .upload-icon {
        font-size: 48px;
        width: 48px;
        height: 48px;
        color: rgba(255,255,255,0.4);
        margin-bottom: 8px;
      }

      p {
        color: rgba(255,255,255,0.6);
        margin: 8px 0 4px;
      }

      .hint {
        color: rgba(255,255,255,0.3);
        font-size: 12px;
      }
    }
  `],
})
export class VideoUploadComponent {
  @Input() uploading = false;
  @Output() fileSelected = new EventEmitter<File>();
  isDragover = false;

  onDragOver(e: DragEvent) {
    e.preventDefault();
    this.isDragover = true;
  }

  onDrop(e: DragEvent) {
    e.preventDefault();
    this.isDragover = false;
    const file = e.dataTransfer?.files[0];
    if (file && file.type === 'video/mp4') {
      this.fileSelected.emit(file);
    }
  }

  onFileSelected(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.fileSelected.emit(file);
    }
    input.value = '';
  }
}
