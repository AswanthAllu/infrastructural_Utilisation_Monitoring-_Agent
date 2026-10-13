export type NavigationTab = 
  | 'overview'
  | 'cpu'
  | 'memory'
  | 'disk'
  | 'bigquery'
  | 'orchestrator'
  | 'alerts';

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type IncidentType = 
  | 'MISSING_PARTITION_FILTER'
  | 'HIGH_CARDINALITY_JOIN'
  | 'SLOT_CONTENTION';

export type JoinFailureMode = 
  | 'KEY_SKEW'
  | 'FAN_OUT'
  | 'SHUFFLE_VOLUME'
  | 'UNCONSTRAINED_JOIN';

export type IncidentConfidence = 
  | 'PATTERN_ONLY'
  | 'PROBABLE'
  | 'CONFIRMED'
  | 'NOT_CONFIRMED'
  | 'INCONCLUSIVE'
  | 'NOT_APPLICABLE';

export type IncidentStatus = 
  | 'DETECTED'
  | 'NOT_DETECTED'
  | 'NOT_APPLICABLE'
  | 'DIAGNOSING'
  | 'DIAGNOSED'
  | 'REMEDIATING'
  | 'REMEDIATION_DRAFTED'
  | 'ESCALATED'
  | 'FAILED';

export type ActionCategory = 
  | 'RECOMMENDATION_ONLY'
  | 'HUMAN_APPROVAL'
  | 'AUTO_FIX';

export interface HealthCheckResponse {
  status: string;
  service: string;
}

export interface MetricSnapshot {
  timestamp: string;
  cpu_percent: number;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
}

export interface ProcessItem {
  pid?: number;
  name?: string;
  process_name?: string;
  cpu_percent?: number;
  memory_percent?: number;
  memory_rss_mb?: number;
  user?: string;
  status?: string;
}

export interface ServiceItem {
  service_name?: string;
  active_state?: string;
  memory_percent?: number;
  memory_rss_mb?: number;
}

export interface CPUDetectionResult {
  detected: boolean;
  incident_type?: IncidentType | string;
  status?: IncidentStatus | string;
  diagnosis_status?: string;
  severity?: Severity | string;
  confidence?: number;
  summary: string;
  root_cause?: string;
  explanation?: string;
  detected_issue?: string;
  evidence?: Record<string, unknown>;
  reasons?: string[];
  safety_notes?: string[];
  crossed_thresholds?: number[];
  escalation_required?: boolean;
  escalation_reason?: string;
  recommended_next_step?: string;
}

export interface CPURemediationResult {
  action_category?: ActionCategory | string;
  status?: IncidentStatus | string;
  action_taken?: string;
  action_required: string;
  preventive_guardrail?: string;
  recommended_query?: string;
  executed?: boolean;
  verification_required?: boolean;
  verification_result?: string;
  workflow_id?: string;
  task_id?: string;
}

export interface RemediationPlanItem {
  plan_id?: string;
  service_name?: string;
  severity?: string;
  root_cause?: string;
  action_required?: string;
  preventive_guardrail?: string;
  memory_usage_percent?: number;
}

export interface AgentAnalysisResponse {
  success?: boolean;
  agent?: string;
  agent_name?: string;
  resource?: string;
  hostname?: string;
  service_name?: string;
  telemetry_type?: 'cpu' | 'disk' | 'memory';
  current_usage_percent?: number;
  peak_usage_percent?: number;
  highest_threshold_crossed?: number | null;
  highest_threshold_exceeded?: string | null;
  alert_dispatched?: boolean;
  alert_recipient?: string;
  total_records_analyzed?: number;
  data_source?: string;
  source_url?: string;
  cpu_utilization_analysis?: string;
  disk_utilization_analysis?: string;
  memory_utilization_analysis?: string;
  detection?: CPUDetectionResult;
  diagnosis?: {
    root_cause?: string;
    explanation?: string;
    severity?: string;
    diagnosis_status?: string;
  };
  remediation?: CPURemediationResult;
  remediation_plans?: RemediationPlanItem[];
  remediation_points?: string[];
  remediation_steps?: string[];
  memory_stats?: {
    service_name?: string;
    hostname?: string;
    current_percent?: number;
    peak_percent?: number;
    used_gb?: number;
    available_gb?: number;
    total_gb?: number;
    threshold_crossed?: number | null;
    primary_process?: ProcessItem;
  };
  disk_stats?: {
    hostname?: string;
    current_percent?: number;
    peak_percent?: number;
    used_gb?: number;
    free_gb?: number;
    total_gb?: number;
    threshold_crossed?: number | null;
  };
  high_memory_processes?: ProcessItem[];
  high_memory_services?: ServiceItem[];
  top_processes?: ProcessItem[];
  service_logs?: Array<Record<string, unknown>>;
  records?: Array<Record<string, unknown>>;
  metrics_analyzed?: {
    current_value?: number;
    threshold_50?: boolean;
    threshold_70?: boolean;
    threshold_100?: boolean;
    history_samples?: number;
  };
  raw_findings?: string[];
}

export interface IncidentRecord {
  incident_id: string;
  incident_type: IncidentType;
  status: IncidentStatus;
  severity: Severity;
  source?: string;
  job_id?: string;
  table_name?: string;
  query?: string;
  summary?: string;
  evidence: Record<string, unknown>;
  metadata: Record<string, unknown>;
  failure_mode?: JoinFailureMode;
}

export interface IncidentReviewResponse {
  region: string;
  lookback_hours: number;
  jobs_analyzed: number;
  incidents_found: number;
  incidents: IncidentRecord[];
}

export interface EmailAlertRecord {
  timestamp: string;
  recipient: string;
  subject: string;
  threshold_level: string;
  metric_name: string;
  value: number;
  status: 'SENT' | 'FAILED' | 'QUEUED';
  details?: string;
}

export interface EmailAlertsResponse {
  total_alerts: number;
  alerts: EmailAlertRecord[];
}

export interface OrchestratorAnalysisResponse {
  workflow_id?: string;
  designated_agent: string;
  routed_by: string;
  workload_classification: string;
  detection: CPUDetectionResult;
  remediation: CPURemediationResult;
  finops_guardrail?: string;
}

export interface MetricsFetchResult {
  success: boolean;
  message: string;
  saved_file: string;
  filename: string;
  records_count: number;
}
