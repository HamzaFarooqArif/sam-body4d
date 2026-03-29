import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, timer, switchMap, takeWhile, map, last } from 'rxjs';

export interface InitVideoResponse {
  session_id: string;
  fps: number;
  total_frames: number;
  first_frame: string; // base64
  width: number;
  height: number;
}

export interface AddPointResponse {
  image: string; // base64
}

export interface AddTargetResponse {
  status: string;
  current_id: number;
}

export interface JobStatusResponse {
  status: 'queued' | 'processing' | 'done' | 'failed';
  progress: number;
  error?: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = '/api';

  constructor(private http: HttpClient) {}

  setBaseUrl(url: string) {
    this.baseUrl = url.replace(/\/$/, '');
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  health(): Observable<{ status: string; server_url?: string }> {
    return this.http.get<{ status: string; server_url?: string }>(`${this.baseUrl}/health`);
  }

  initVideo(file: File): Observable<InitVideoResponse> {
    const formData = new FormData();
    formData.append('video', file);
    return this.http.post<InitVideoResponse>(`${this.baseUrl}/init_video`, formData);
  }

  getFrame(sessionId: string, frameIdx: number): Observable<{ frame: string }> {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('frame_idx', frameIdx.toString());
    return this.http.post<{ frame: string }>(`${this.baseUrl}/get_frame`, formData);
  }

  addPoint(
    sessionId: string,
    frameIdx: number,
    x: number,
    y: number,
    pointType: string,
    width: number,
    height: number,
  ): Observable<AddPointResponse> {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('frame_idx', frameIdx.toString());
    formData.append('x', Math.round(x).toString());
    formData.append('y', Math.round(y).toString());
    formData.append('point_type', pointType);
    formData.append('width', width.toString());
    formData.append('height', height.toString());
    return this.http.post<AddPointResponse>(`${this.baseUrl}/add_point`, formData);
  }



  addTarget(sessionId: string): Observable<AddTargetResponse> {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    return this.http.post<AddTargetResponse>(`${this.baseUrl}/add_target`, formData);
  }

  generateMasksAsync(sessionId: string, frameStep: number = 1): Observable<{ job_id: string }> {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('frame_step', frameStep.toString());
    return this.http.post<{ job_id: string }>(`${this.baseUrl}/session_generate_masks_async`, formData);
  }

  generate4dAsync(sessionId: string, frameStep: number = 1): Observable<{ job_id: string }> {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('frame_step', frameStep.toString());
    return this.http.post<{ job_id: string }>(`${this.baseUrl}/session_generate_4d_async`, formData);
  }

  getJobStatus(jobId: string): Observable<JobStatusResponse> {
    return this.http.get<JobStatusResponse>(`${this.baseUrl}/job/${jobId}`);
  }

  getJobResultUrl(jobId: string): string {
    return `${this.baseUrl}/job/${jobId}/result`;
  }

  pollJob(jobId: string, intervalMs: number = 3000): Observable<JobStatusResponse> {
    return timer(0, intervalMs).pipe(
      switchMap(() => this.getJobStatus(jobId)),
      takeWhile(res => res.status !== 'done' && res.status !== 'failed', true),
    );
  }

  getJobResultBlob(jobId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/job/${jobId}/result`, { responseType: 'blob' });
  }

  deleteSession(sessionId: string): Observable<any> {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    return this.http.post(`${this.baseUrl}/delete_session`, formData);
  }
}
