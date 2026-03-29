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

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    MatToolbarModule, MatInputModule, MatFormFieldModule, MatButtonModule, MatIconModule, MatSnackBarModule,
    VideoUploadComponent, FrameViewerComponent, ControlsComponent, ResultsComponent,
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
  private currentVideoFile: File | null = null;

  connected = signal(false);
  isLocalDev = window.location.hostname === 'localhost';
  apiUrlInput = '';
  currentApiUrl = signal('/api');
  uploading = signal(false);

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

  onFileSelected(file: File) {
    this.uploading.set(true);
    this.session.reset();
    this.maskVideoUrl.set(null);
    this.fourDVideoUrl.set(null);
    this.pointMarkers.set([]);
    this.currentVideoFile = file;

    this.api.initVideo(file).subscribe({
      next: async (res) => {
        this.session.sessionId.set(res.session_id);
        this.session.fps.set(res.fps);
        this.session.totalFrames.set(res.total_frames);
        this.session.videoWidth.set(res.width);
        this.session.videoHeight.set(res.height);
        this.currentFrameSrc.set('data:image/png;base64,' + res.first_frame);

        // Load video locally for fast frame scrubbing
        await this.frameExtractor.loadVideo(file, res.fps);

        this.uploading.set(false);
        this.snackBar.open(`Video loaded: ${res.total_frames} frames`, '', { duration: 2000 });
      },
      error: (err) => {
        this.uploading.set(false);
        this.snackBar.open('Upload failed: ' + (err.error?.error || err.message), '', { duration: 5000 });
      },
    });
  }

  async onFrameChange(idx: number) {
    this.session.currentFrameIdx.set(idx);
    // Map reduced frame index to original: frame 5 at step 2 = original frame 10
    const originalIdx = idx * this.session.frameStep();
    try {
      const dataUrl = await this.frameExtractor.getFrame(originalIdx);
      this.currentFrameSrc.set(dataUrl);
    } catch {
      const sid = this.session.sessionId();
      if (sid) {
        this.api.getFrame(sid, originalIdx).subscribe({
          next: (res) => this.currentFrameSrc.set('data:image/png;base64,' + res.frame),
          error: () => {},
        });
      }
    }
  }

  onFrameClick(coords: { x: number; y: number }) {
    const sid = this.session.sessionId();
    if (!sid || this.annotating()) return;

    // Add new marker locally
    const newMarker: PointMarker = {
      x: coords.x,
      y: coords.y,
      type: this.session.pointType(),
      targetId: this.session.currentTargetId(),
      frameIdx: this.session.currentFrameIdx(),
    };
    const updated = [...this.pointMarkers(), newMarker];
    this.pointMarkers.set(updated);
    this.syncPointsWithPod(updated);
  }

  onMarkerRemove(markerIdx: number) {
    const sid = this.session.sessionId();
    if (!sid || this.annotating()) return;

    const updated = this.pointMarkers().filter((_, i) => i !== markerIdx);
    this.pointMarkers.set(updated);

    if (updated.length === 0) {
      this.onFrameChange(this.session.currentFrameIdx());
      return;
    }
    this.syncPointsWithPod(updated);
  }

  private syncPointsWithPod(markers: PointMarker[]) {
    const sid = this.session.sessionId();
    if (!sid) return;

    this.annotating.set(true);
    this.cdr.detectChanges();

    const points = markers.map(m => ({
      frame_idx: m.frameIdx * this.session.frameStep(),
      x: Math.round(m.x),
      y: Math.round(m.y),
      type: m.type,
      target_id: m.targetId,
      width: this.session.videoWidth(),
      height: this.session.videoHeight(),
    }));

    this.api.setPoints(sid, points).subscribe({
      next: (res) => {
        if (res.image) {
          this.currentFrameSrc.set('data:image/png;base64,' + res.image);
        }
        this.annotating.set(false);
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.snackBar.open('Annotation failed: ' + (err.error?.error || ''), '', { duration: 3000 });
        this.annotating.set(false);
        this.cdr.detectChanges();
      },
    });
  }

  onAddTarget() {
    // Local only — set_points handles target grouping on the pod
    const currentId = this.session.currentTargetId();
    this.session.targets.update(t => [...t, `Target ${currentId}`]);
    this.session.currentTargetId.set(currentId + 1);
    this.snackBar.open(`Target ${currentId} added. Click on next person.`, '', { duration: 2000 });
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
