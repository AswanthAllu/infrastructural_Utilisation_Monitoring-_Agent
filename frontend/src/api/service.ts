import type {
  AgentAnalysisResponse,
  EmailAlertsResponse,
  HealthCheckResponse,
  IncidentReviewResponse,
  MetricsFetchResult,
  OrchestratorAnalysisResponse,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'localhost:8000';

class ApiService {
  private baseUrl: string;
  private apiKey: string;

  constructor() {
    this.baseUrl = BASE_URL.replace(/\/$/, '');
    this.apiKey = API_KEY;
  }

  private getHeaders(contentType = 'application/json'): HeadersInit {
    return {
      'Content-Type': contentType,
      'X-API-Key': this.apiKey,
      Accept: 'application/json',
    };
  }

  async checkHealth(): Promise<HealthCheckResponse> {
    const res = await fetch(`${this.baseUrl}/health`, {
      headers: this.getHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      throw new Error(`Health check failed: HTTP ${res.status} ${res.statusText}`);
    }
    return await res.json();
  }

  async triggerMetricsFetch(): Promise<MetricsFetchResult> {
    const res = await fetch(`${this.baseUrl}/api/metrics/fetch`, {
      method: 'POST',
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`Failed to fetch live telemetry: ${errorText}`);
    }
    return await res.json();
  }

  async getEmailAlerts(): Promise<EmailAlertsResponse> {
    const res = await fetch(`${this.baseUrl}/api/metrics/alerts`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`Failed to load email alerts from API: ${errorText}`);
    }
    return await res.json();
  }

  async analyzeCpu(customText?: string): Promise<AgentAnalysisResponse> {
    let res: Response;
    if (customText) {
      const formData = new FormData();
      formData.append('text', customText);
      res = await fetch(`${this.baseUrl}/api/cpu/analyze`, {
        method: 'POST',
        body: formData,
      });
    } else {
      res = await fetch(`${this.baseUrl}/api/cpu/analyze`, {
        method: 'GET',
        headers: this.getHeaders(),
      });
    }
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`CPU Agent API error (HTTP ${res.status}): ${errorText}`);
    }
    return await res.json();
  }

  async analyzeDisk(): Promise<AgentAnalysisResponse> {
    const res = await fetch(`${this.baseUrl}/api/disk/analyze`, {
      method: 'GET',
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`Disk Agent API error (HTTP ${res.status}): ${errorText}`);
    }
    return await res.json();
  }

  async analyzeMemory(): Promise<AgentAnalysisResponse> {
    const res = await fetch(`${this.baseUrl}/api/memory/analyze`, {
      method: 'GET',
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`Memory Agent API error (HTTP ${res.status}): ${errorText}`);
    }
    return await res.json();
  }

  async reviewIncidents(
    region = 'US',
    lookbackHours = 24,
    jobsLimit = 5
  ): Promise<IncidentReviewResponse> {
    const url = new URL(`${this.baseUrl}/api/review`);
    url.searchParams.append('region', region);
    url.searchParams.append('lookback_hours', String(lookbackHours));
    url.searchParams.append('jobs_limit', String(jobsLimit));

    const res = await fetch(url.toString(), {
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`Incident review failed: ${errorText}`);
    }
    return await res.json();
  }

  async runOrchestratorAnalysis(
    input: { text?: string; file?: File; filename?: string }
  ): Promise<OrchestratorAnalysisResponse> {
    let res: Response;
    if (input.file) {
      const formData = new FormData();
      formData.append('file', input.file);
      res = await fetch(`${this.baseUrl}/api/orchestrator/analyze`, {
        method: 'POST',
        body: formData,
      });
    } else {
      const formData = new FormData();
      formData.append('text', input.text || '');
      res = await fetch(`${this.baseUrl}/api/orchestrator/analyze`, {
        method: 'POST',
        body: formData,
      });
    }
    if (!res.ok) {
      const errorText = await res.text().catch(() => res.statusText);
      throw new Error(`Orchestration API error: ${errorText}`);
    }
    return await res.json();
  }
}

export const apiService = new ApiService();
export default apiService;
