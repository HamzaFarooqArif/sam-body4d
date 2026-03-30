import { Component, signal, inject, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { ApiService, JobStatusResponse } from './services/api.service';
import { SessionService } from './services/session.service';
import { FrameExtractorService } from './services/frame-extractor.service';
import { VideoUploadComponent } from './components/video-upload/video-upload.component';
import { FrameViewerComponent, PointMarker } from './components/frame-viewer/frame-viewer.component';
import { ControlsComponent } from './components/controls/controls.component';
import { ResultsComponent } from './components/results/results.component';
import { ExamplesComponent } from './components/examples/examples.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatToolbarModule, MatInputModule, MatFormFieldModule, MatButtonModule, MatIconModule, MatSnackBarModule,
    VideoUploadComponent, FrameViewerComponent, ControlsComponent, ResultsComponent, ExamplesComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private api = inject(ApiService);
  private snackBar = inject(MatSnackBar);
  private frameExtractor = inject(FrameExtractorService);
  private cdr = inject(ChangeDetectorRef);
  session = inject(SessionService);
  currentVideoFile: File | null = null;

  connected = signal(false);
  isLocalDev = window.location.hostname === 'localhost';
  apiUrlInput = '';
  currentApiUrl = signal('/api');
  uploading = signal(false);
  exampleLoadingName = signal<string | null>(null);

  currentFrameSrc = signal<string | null>(null);
  pointMarkers = signal<PointMarker[]>([]);
  annotating = signal(false);
  maskVideoUrl = signal<string | null>(null);
  fourDVideoUrl = signal<string | null>(null);

  maskGenerating = signal(false);
  maskProgress = signal(0);
  maskElapsed = signal('');
  fourDGenerating = signal(false);
  fourDProgress = signal(0);
  fourDElapsed = signal('');

  ngOnInit() {
    // Restore saved pod URL for local dev
    if (this.isLocalDev) {
      const saved = localStorage.getItem('sam_body4d_pod_url');
      if (saved) {
        this.apiUrlInput = saved;
        const apiUrl = saved.includes('/api') ? saved : saved + '/api';
        this.api.setBaseUrl(apiUrl);
        this.currentApiUrl.set(apiUrl);
      }
    }
    this.checkConnection();
  }

  applyApiUrl() {
    const url = this.apiUrlInput.trim().replace(/\/$/, '');
    if (url) {
      const apiUrl = url.includes('/api') ? url : url + '/api';
      this.api.setBaseUrl(apiUrl);
      this.currentApiUrl.set(apiUrl);
      localStorage.setItem('sam_body4d_pod_url', url);
    } else {
      this.api.setBaseUrl('/api');
      this.currentApiUrl.set('/api (proxy)');
      localStorage.removeItem('sam_body4d_pod_url');
    }
    this.checkConnection();
  }

  checkConnection() {
    this.api.health().subscribe({
      next: (res) => {
        this.connected.set(true);
        if (res.server_url) {
          this.currentApiUrl.set(res.server_url);
        }
        this.snackBar.open('Connected to ' + (res.server_url || 'server'), '', { duration: 2000 });
      },
      error: () => {
        this.connected.set(false);
        this.snackBar.open('Cannot reach server', '', { duration: 3000 });
      },
    });
  }

  async onExampleSelected(filename: string) {
    this.exampleLoadingName.set(filename);
    try {
      // Load locally using URL directly (no blob conversion)
      this.session.reset();
      this.maskVideoUrl.set(null);
      this.fourDVideoUrl.set(null);
      this.pointMarkers.set([]);

      const url = `/examples/${filename}`;
      const fps = 30;
      await this.frameExtractor.loadVideo(url, fps);

      const videoEl = (this.frameExtractor as any).videoEl as HTMLVideoElement;
      const duration = videoEl.duration || 1;
      const totalFrames = Math.round(duration * fps);

      this.session.fps.set(fps);
      this.session.totalFrames.set(totalFrames);
      this.session.rangeStart.set(0);
      this.session.rangeEnd.set(totalFrames);
      this.session.videoWidth.set(videoEl.videoWidth);
      this.session.videoHeight.set(videoEl.videoHeight);
      this.session.currentFrameIdx.set(0);

      const firstFrame = await this.frameExtractor.getFrame(0);
      this.currentFrameSrc.set(firstFrame);

      // Fetch as file for Apply & Upload later
      const response = await fetch(url);
      const blob = await response.blob();
      this.currentVideoFile = new File([blob], filename, { type: 'video/mp4' });

      this.snackBar.open(`Example loaded: ${totalFrames} frames`, '', { duration: 3000 });
    } catch (e) {
      console.error('Example load failed:', e);
      this.snackBar.open('Failed to load example', '', { duration: 3000 });
    }
    this.exampleLoadingName.set(null);
  }

  async onFileSelected(file: File) {
    // Local only — no backend upload yet
    this.session.reset();
    this.maskVideoUrl.set(null);
    this.fourDVideoUrl.set(null);
    this.pointMarkers.set([]);
    this.currentVideoFile = file;

    try {
      // Use frame extractor to load — it creates a video element internally
      const fps = 30; // estimate, corrected by backend after Apply
      await this.frameExtractor.loadVideo(file, fps);

      // Get metadata from frame extractor's video element
      const videoEl = (this.frameExtractor as any).videoEl as HTMLVideoElement;
      const duration = videoEl.duration || 1;
      const totalFrames = Math.round(duration * fps);

      this.session.fps.set(fps);
      this.session.totalFrames.set(totalFrames);
      this.session.rangeStart.set(0);
      this.session.rangeEnd.set(totalFrames);
      this.session.videoWidth.set(videoEl.videoWidth);
      this.session.videoHeight.set(videoEl.videoHeight);
      this.session.currentFrameIdx.set(0);

      const firstFrame = await this.frameExtractor.getFrame(0);
      this.currentFrameSrc.set(firstFrame);

      this.snackBar.open(`Video loaded: ${totalFrames} frames. Adjust range/framerate and click Apply & Upload.`, '', { duration: 4000 });
    } catch (e: any) {
      this.frameExtractor.cleanup();
      this.currentVideoFile = null;
      const msg = e?.message || e?.toString() || 'Unknown error';
      console.error('Video load failed:', e);
      this.snackBar.open('Failed to load video: ' + msg, '', { duration: 5000 });
    }
  }

  applying = signal(false);

  async onApplySettings() {
    const file = this.currentVideoFile;
    if (!file) return;

    // Delete old session
    const oldSid = this.session.sessionId();
    if (oldSid) {
      this.api.deleteSession(oldSid).subscribe();
    }

    this.applying.set(true);
    this.session.sessionId.set(null);
    this.pointMarkers.set([]);
    this.maskVideoUrl.set(null);
    this.fourDVideoUrl.set(null);
    this.session.annotationFrameIdx.set(null);
    this.session.targets.set([]);
    this.session.currentTargetId.set(1);

    const rangeStart = this.session.rangeStart();
    const rangeEnd = this.session.rangeEnd();
    const frameStep = this.session.frameStep();

    try {
      // Trim video: extract range + framerate into a new file
      const trimmedFile = await this.trimVideo(file, rangeStart, rangeEnd, frameStep);

      // Upload trimmed video to backend
      this.api.initVideo(trimmedFile).subscribe({
        next: async (res) => {
          this.session.sessionId.set(res.session_id);
          this.session.fps.set(res.fps);
          this.session.videoWidth.set(res.width);
          this.session.videoHeight.set(res.height);

          // Load trimmed video for scrubbing
          try {
            await this.frameExtractor.loadVideo(trimmedFile, res.fps);
          } catch {
            this.frameExtractor.cleanup();
          }

          // Update total frames to trimmed count
          this.session.totalFrames.set(res.total_frames);
          this.session.rangeStart.set(0);
          this.session.rangeEnd.set(res.total_frames);
          // Keep frameStep — backend uses it during generation
          this.session.currentFrameIdx.set(0);
          this.currentFrameSrc.set('data:image/png;base64,' + res.first_frame);

          this.applying.set(false);
          this.snackBar.open(`Uploaded: ${res.total_frames} frames`, '', { duration: 2000 });
        },
        error: (err) => {
          this.applying.set(false);
          this.snackBar.open('Upload failed: ' + (err.error?.error || err.message), '', { duration: 5000 });
        },
      });
    } catch {
      this.applying.set(false);
      this.snackBar.open('Failed to trim video', '', { duration: 3000 });
    }
  }

  private async trimVideo(file: File, rangeStart: number, rangeEnd: number, _frameStep: number): Promise<File> {
    // Only trim range — frameStep handled by backend
    const totalFrames = this.session.totalFrames();
    if (rangeStart === 0 && rangeEnd === totalFrames) {
      return file;
    }

    const fps = this.session.fps();
    const videoEl = document.createElement('video');
    videoEl.muted = true;
    videoEl.src = URL.createObjectURL(file);
    await new Promise<void>(r => { videoEl.onloadedmetadata = () => r(); });

    const canvas = document.createElement('canvas');
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext('2d')!;

    // Collect frames — every frame in range (frameStep handled by backend)
    const frames: Blob[] = [];
    const outputFps = fps;

    for (let i = rangeStart; i < rangeEnd; i++) {
      videoEl.currentTime = i / fps;
      await new Promise<void>(r => { videoEl.onseeked = () => r(); });
      ctx.drawImage(videoEl, 0, 0);
      const blob = await new Promise<Blob>((r) => canvas.toBlob(b => r(b!), 'image/jpeg', 0.9));
      frames.push(blob);
    }

    URL.revokeObjectURL(videoEl.src);

    // Encode frames to video using MediaRecorder
    const stream = canvas.captureStream(outputFps);
    const recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9' });
    const chunks: Blob[] = [];

    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

    const recordingDone = new Promise<void>(r => { recorder.onstop = () => r(); });
    recorder.start();

    for (let i = 0; i < frames.length; i++) {
      const img = new Image();
      img.src = URL.createObjectURL(frames[i]);
      await new Promise<void>(r => { img.onload = () => r(); });
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(img.src);
      // Wait one frame duration
      await new Promise(r => setTimeout(r, 1000 / outputFps));
    }

    recorder.stop();
    stream.getTracks().forEach(t => t.stop());
    await recordingDone;

    const webmBlob = new Blob(chunks, { type: 'video/webm' });
    return new File([webmBlob], 'trimmed.webm', { type: 'video/webm' });
  }

  private frameChangeTimer: any = null;

  onFrameChange(idx: number) {
    this.session.currentFrameIdx.set(idx);

    // Debounce — wait 150ms after last slider move
    clearTimeout(this.frameChangeTimer);
    this.frameChangeTimer = setTimeout(() => this.loadFrame(idx), 150);
  }

  private async loadFrame(idx: number) {
    const originalIdx = idx * this.session.frameStep();
    try {
      const dataUrl = await this.frameExtractor.getFrame(originalIdx);
      this.currentFrameSrc.set(dataUrl);
      this.cdr.detectChanges();
    } catch {
      const sid = this.session.sessionId();
      if (sid) {
        this.api.getFrame(sid, originalIdx).subscribe({
          next: (res) => {
            this.currentFrameSrc.set('data:image/png;base64,' + res.frame);
            this.cdr.detectChanges();
          },
          error: () => {},
        });
      }
    }
  }

  onFrameClick(coords: { x: number; y: number }) {
    const sid = this.session.sessionId();
    if (!sid || this.annotating()) return;

    const frameIdx = this.session.currentFrameIdx();
    const lockedFrame = this.session.annotationFrameIdx();

    // Lock annotations to the first frame where a point was placed
    if (lockedFrame !== null && frameIdx !== lockedFrame) {
      this.snackBar.open(`All annotations must be on frame ${lockedFrame}. Navigate there or upload video again.`, '', { duration: 4000 });
      return;
    }

    this.annotating.set(true);
    this.cdr.detectChanges();

    // Lock to this frame on first click
    if (lockedFrame === null) {
      this.session.annotationFrameIdx.set(frameIdx);
    }

    const pointType = this.session.pointType();
    const targetId = this.session.currentTargetId();
    const originalIdx = frameIdx * this.session.frameStep();

    this.api.addPoint(
      sid, originalIdx, coords.x, coords.y, pointType,
      this.session.videoWidth(), this.session.videoHeight(),
    ).subscribe({
      next: (res) => {
        this.currentFrameSrc.set('data:image/png;base64,' + res.image);
        this.pointMarkers.update(markers => [
          ...markers,
          { x: coords.x, y: coords.y, type: pointType, targetId, frameIdx }
        ]);
        this.annotating.set(false);
        this.cdr.detectChanges();
      },
      error: (err) => {
        const msg = err.error?.error || err.message || '';
        if (msg.includes('Cannot add new object') || msg.includes('after tracking')) {
          this.snackBar.open('Cannot add targets after mask generation. Upload video again to start over.', '', { duration: 5000 });
        } else {
          this.snackBar.open('Annotation failed: ' + msg, '', { duration: 3000 });
        }
        this.annotating.set(false);
        this.cdr.detectChanges();
      },
    });
  }

  onMarkerRemove(_markerIdx: number) {
    this.snackBar.open('Point removal not supported. Upload video again to start over.', '', { duration: 3000 });
  }

  resetting = signal(false);

  onResetTargets() {
    const file = this.currentVideoFile;
    if (!file || this.resetting()) return;

    this.resetting.set(true);

    // Delete old session to free GPU memory
    const oldSid = this.session.sessionId();
    if (oldSid) {
      this.api.deleteSession(oldSid).subscribe();
    }

    this.pointMarkers.set([]);
    this.session.targets.set([]);
    this.session.currentTargetId.set(1);
    this.session.annotationFrameIdx.set(null);
    this.maskVideoUrl.set(null);
    this.fourDVideoUrl.set(null);

    // Re-init session on pod with same video
    this.api.initVideo(file).subscribe({
      next: async (res) => {
        this.session.sessionId.set(res.session_id);
        this.currentFrameSrc.set('data:image/png;base64,' + res.first_frame);
        this.session.currentFrameIdx.set(0);
        this.resetting.set(false);
        this.snackBar.open('Reset complete', '', { duration: 1500 });
      },
      error: () => {
        this.resetting.set(false);
        this.snackBar.open('Reset failed', '', { duration: 3000 });
      },
    });
  }

  onAddTarget() {
    const sid = this.session.sessionId();
    if (!sid) return;

    this.api.addTarget(sid).subscribe({
      next: (res) => {
        this.session.targets.update(t => [...t, `Target ${t.length + 1}`]);
        this.session.currentTargetId.set(res.current_id);
        this.snackBar.open('Target added', '', { duration: 1500 });
      },
      error: () => {},
    });
  }

  async onApplyFrameRate(pct: number) {
    const step = Math.max(1, Math.round(100 / pct));
    this.session.frameStep.set(step);
    this.session.currentFrameIdx.set(0);

    // Show first frame at new framerate
    try {
      const dataUrl = await this.frameExtractor.getFrame(0);
      this.currentFrameSrc.set(dataUrl);
    } catch {}

    this.snackBar.open(`Frame rate: ${pct}% (${this.session.effectiveFrames()} frames, step ${step})`, '', { duration: 2000 });
  }

  onGenerateMasks() {
    const sid = this.session.sessionId();
    if (!sid) return;

    this.maskGenerating.set(true);
    this.maskProgress.set(0);
    this.maskVideoUrl.set(null);
    const startTime = Date.now();

    this.api.generateMasksAsync(sid, this.session.frameStep()).subscribe({
      next: (res) => {
        this.pollJob(res.job_id, startTime, this.maskProgress, this.maskElapsed, () => {
          this.maskVideoUrl.set(this.api.getJobResultUrl(res.job_id));
          this.maskGenerating.set(false);
          this.snackBar.open('Mask generation complete!', '', { duration: 3000 });
        }, () => {
          this.maskGenerating.set(false);
        });
      },
      error: (err) => {
        this.maskGenerating.set(false);
        this.snackBar.open('Failed: ' + (err.error?.error || err.message), '', { duration: 5000 });
      },
    });
  }

  onGenerate4d() {
    const sid = this.session.sessionId();
    if (!sid) return;

    this.fourDGenerating.set(true);
    this.fourDProgress.set(0);
    this.fourDVideoUrl.set(null);
    const startTime = Date.now();

    this.api.generate4dAsync(sid, this.session.frameStep()).subscribe({
      next: (res) => {
        this.pollJob(res.job_id, startTime, this.fourDProgress, this.fourDElapsed, () => {
          // 4D result is a zip — download and extract video
          this.api.getJobResultBlob(res.job_id).subscribe({
            next: async (blob) => {
              try {
                const { BlobReader, ZipReader, BlobWriter } = await import('@zip.js/zip.js');
                const reader = new ZipReader(new BlobReader(blob));
                const entries = await reader.getEntries();
                const videoEntry = entries.find(e => e.filename.endsWith('.mp4'));
                if (videoEntry && 'getData' in videoEntry) {
                  const videoBlob = await (videoEntry as any).getData(new BlobWriter('video/mp4'));
                  this.fourDVideoUrl.set(URL.createObjectURL(videoBlob));
                } else {
                  this.snackBar.open('No video found in results', '', { duration: 3000 });
                }
                await reader.close();
              } catch {
                // Fallback — might be a direct video file, not zip
                this.fourDVideoUrl.set(URL.createObjectURL(blob));
              }
              this.fourDGenerating.set(false);
              this.snackBar.open('4D generation complete!', '', { duration: 3000 });
            },
            error: () => {
              this.fourDGenerating.set(false);
              this.snackBar.open('Failed to download result', '', { duration: 3000 });
            },
          });
        }, () => {
          this.fourDGenerating.set(false);
        });
      },
      error: (err) => {
        this.fourDGenerating.set(false);
        this.snackBar.open('Failed: ' + (err.error?.error || err.message), '', { duration: 5000 });
      },
    });
  }

  private pollJob(
    jobId: string,
    startTime: number,
    progressSignal: ReturnType<typeof signal<number>>,
    elapsedSignal: ReturnType<typeof signal<string>>,
    onDone: () => void,
    onFail: () => void,
  ) {
    this.api.pollJob(jobId).subscribe({
      next: (status: JobStatusResponse) => {
        const elapsed = (Date.now() - startTime) / 1000;
        const mins = Math.floor(elapsed / 60);
        const secs = Math.floor(elapsed % 60);
        elapsedSignal.set(mins > 0 ? `${mins}m ${secs}s` : `${secs}s`);
        progressSignal.set(status.progress || 0);

        if (status.status === 'done') {
          progressSignal.set(100);
          onDone();
        } else if (status.status === 'failed') {
          this.snackBar.open('Job failed: ' + (status.error || 'Unknown'), '', { duration: 5000 });
          onFail();
        }
      },
      error: () => onFail(),
    });
  }
}
