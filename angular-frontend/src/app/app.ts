import { Component, signal, inject, OnInit } from '@angular/core';
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
import { VideoUploadComponent } from './components/video-upload/video-upload.component';
import { FrameViewerComponent } from './components/frame-viewer/frame-viewer.component';
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
  session = inject(SessionService);

  apiUrl = 'http://localhost:8000';
  connected = signal(false);
  uploading = signal(false);

  currentFrameSrc = signal<string | null>(null);
  maskVideoUrl = signal<string | null>(null);
  fourDVideoUrl = signal<string | null>(null);

  maskGenerating = signal(false);
  maskProgress = signal(0);
  maskElapsed = signal('');
  fourDGenerating = signal(false);
  fourDProgress = signal(0);
  fourDElapsed = signal('');

  ngOnInit() {
    const saved = localStorage.getItem('sam_body4d_api_url');
    if (saved) {
      this.apiUrl = saved;
    }
    this.checkConnection();
  }

  checkConnection() {
    this.api.setBaseUrl(this.apiUrl);
    localStorage.setItem('sam_body4d_api_url', this.apiUrl);
    this.api.health().subscribe({
      next: () => {
        this.connected.set(true);
        this.snackBar.open('Connected to server', '', { duration: 2000 });
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

    this.api.initVideo(file).subscribe({
      next: (res) => {
        this.session.sessionId.set(res.session_id);
        this.session.fps.set(res.fps);
        this.session.totalFrames.set(res.total_frames);
        this.session.videoWidth.set(res.width);
        this.session.videoHeight.set(res.height);
        this.currentFrameSrc.set('data:image/png;base64,' + res.first_frame);
        this.uploading.set(false);
        this.snackBar.open(`Video loaded: ${res.total_frames} frames`, '', { duration: 2000 });
      },
      error: (err) => {
        this.uploading.set(false);
        this.snackBar.open('Upload failed: ' + (err.error?.error || err.message), '', { duration: 5000 });
      },
    });
  }

  onFrameChange(idx: number) {
    const sid = this.session.sessionId();
    if (!sid) return;
    this.session.currentFrameIdx.set(idx);
    this.api.getFrame(sid, idx).subscribe({
      next: (res) => this.currentFrameSrc.set('data:image/png;base64,' + res.frame),
      error: () => {},
    });
  }

  onFrameClick(coords: { x: number; y: number }) {
    const sid = this.session.sessionId();
    if (!sid) return;

    this.api.addPoint(
      sid,
      this.session.currentFrameIdx(),
      coords.x,
      coords.y,
      this.session.pointType(),
      this.session.videoWidth(),
      this.session.videoHeight(),
    ).subscribe({
      next: (res) => this.currentFrameSrc.set('data:image/png;base64,' + res.image),
      error: (err) => this.snackBar.open('Annotation failed: ' + (err.error?.error || ''), '', { duration: 3000 }),
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

  onApplyFrameRate(pct: number) {
    const step = Math.max(1, Math.round(100 / pct));
    this.session.frameStep.set(step);
    this.snackBar.open(`Frame step set to ${step} (${pct}%)`, '', { duration: 2000 });
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
