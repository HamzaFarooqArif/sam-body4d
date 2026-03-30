import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class FrameExtractorService {
  private videoEl: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private videoUrl: string | null = null;
  private fps = 30;

  async loadVideo(file: File | Blob | string, fps: number): Promise<void> {
    this.cleanup();
    this.fps = fps;

    // Accept File, Blob, or URL string
    if (typeof file === 'string') {
      this.videoUrl = file;
    } else {
      this.videoUrl = URL.createObjectURL(file);
    }

    this.videoEl = document.createElement('video');
    this.videoEl.muted = true;
    this.videoEl.preload = 'auto';
    this.videoEl.src = this.videoUrl;
    this.videoEl.load();

    this.canvas = document.createElement('canvas');
    this.ctx = this.canvas.getContext('2d');

    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Video load timeout')), 10000);
      this.videoEl!.onloadedmetadata = () => {
        clearTimeout(timeout);
        this.canvas!.width = this.videoEl!.videoWidth;
        this.canvas!.height = this.videoEl!.videoHeight;
        resolve();
      };
      this.videoEl!.onerror = (e) => {
        clearTimeout(timeout);
        const mediaError = this.videoEl?.error;
        const code = mediaError?.code;
        const message = mediaError?.message;
        const codes: Record<number, string> = {
          1: 'MEDIA_ERR_ABORTED',
          2: 'MEDIA_ERR_NETWORK',
          3: 'MEDIA_ERR_DECODE',
          4: 'MEDIA_ERR_SRC_NOT_SUPPORTED',
        };
        const errorDetail = `code=${code} (${codes[code || 0] || 'UNKNOWN'}), message="${message || 'none'}", src="${this.videoEl?.src?.substring(0, 100)}"`;
        console.error('Video element error:', errorDetail, e);
        reject(new Error('Failed to load video: ' + errorDetail));
      };
    });
  }

  async getFrame(frameIdx: number): Promise<string> {
    if (!this.videoEl || !this.canvas || !this.ctx) {
      throw new Error('No video loaded');
    }

    const time = frameIdx / this.fps;
    this.videoEl.currentTime = time;

    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Seek timeout')), 5000);
      this.videoEl!.onseeked = () => {
        clearTimeout(timeout);
        resolve();
      };
    });

    this.ctx.drawImage(this.videoEl, 0, 0);
    return this.canvas.toDataURL('image/png');
  }

  cleanup() {
    if (this.videoUrl) {
      URL.revokeObjectURL(this.videoUrl);
      this.videoUrl = null;
    }
    this.videoEl = null;
    this.canvas = null;
    this.ctx = null;
  }
}
