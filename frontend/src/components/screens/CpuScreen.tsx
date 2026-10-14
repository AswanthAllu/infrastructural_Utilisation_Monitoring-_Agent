import React, { useState } from 'react';
import {
  Activity,
  Play,
  RefreshCw,
  Server,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { RemediationList } from '../common/RemediationList';
import type { AgentAnalysisResponse } from '../../types';

interface CpuScreenProps {
  data: AgentAnalysisResponse | null;
  isLoading: boolean;
  onRunAnalysis: (customInput?: string) => void;
  lastUpdated?: string;
}

export const CpuScreen: React.FC<CpuScreenProps> = ({
  data,
  isLoading,
  onRunAnalysis,
  lastUpdated: _lastUpdated,
}) => {
  const [customCsvInput, setCustomCsvInput] = useState('');
  const [showInputBox] = useState(false);

  const currentUsageVal =
    data?.current_usage_percent ?? (data?.metrics_analyzed?.current_value ?? 0);
  const peakUsageVal = data?.peak_usage_percent ?? currentUsageVal;

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          {/* <div className="flex flex-wrap items-center gap-2">
            <Badge variant="primary" size="sm">
              DIRECT 3-SUBAGENT PIPELINE
            </Badge>
            <span className="text-xs font-mono text-muted-foreground">/api/cpu/analyze</span>
            {lastUpdated && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--success)] border border-[var(--success)]/20">
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)]"></span>
                Cached: {lastUpdated}
              </span>
            )}
          </div> */}
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            CPU Utilization Agent
          </h2>
        </div>

        <div className="flex items-center gap-2">
          {/* <button
            onClick={() => setShowInputBox(!showInputBox)}
            className="rounded-[var(--radius-md)] border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
          >
            {showInputBox ? 'Hide Custom Input' : 'Paste Telemetry / CSV'}
          </button> */}
          <button
            onClick={() => onRunAnalysis(showInputBox && customCsvInput ? customCsvInput : undefined)}
            disabled={isLoading}
            className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[var(--primary-hover)] disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? 'Rerunning CPU Agent...' : 'Rerun CPU Agent'}</span>
          </button>
        </div>
      </div>

      {/* Optional Custom Input Box */}
      {showInputBox && (
        <Card title="Custom Telemetry Log Input" subtitle="Supply custom JSON telemetry or BigQuery CPU execution logs">
          <textarea
            value={customCsvInput}
            onChange={(e) => setCustomCsvInput(e.target.value)}
            placeholder={`timestamp,metric_type,project_id,job_id,avg_slots_utilized,total_slot_ms,runtime_seconds,query\n2026-10-12 14:00:00,BQ_CPU_USAGE,analytics-prod,bqjob_9812,18.4,4920192,160.0,"SELECT * FROM events"`}
            rows={4}
            className="w-full rounded-[var(--radius-md)] border border-border bg-muted/20 p-3 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
          />
          <div className="mt-2 flex justify-end">
            <button
              onClick={() => onRunAnalysis(customCsvInput)}
              disabled={isLoading || !customCsvInput.trim()}
              className="flex items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--primary)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--primary-hover)] disabled:opacity-50"
            >
              <Play className="h-3 w-3" />
              <span>Submit to CPU Agent</span>
            </button>
          </div>
        </Card>
      )}

      {/* Single Live Card: Current CPU Utilization Value */}
      <div className="rounded-[var(--radius-xl)] border border-border bg-card p-6 shadow-[var(--shadow-resting)]">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--primary)]/10 text-[var(--primary)] border border-[var(--primary)]/20 shadow-sm">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Live Telemetry Evaluation
              </span>
              <h3 className="font-heading text-lg font-bold text-foreground">
                Current CPU Utilization Value
              </h3>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge
              variant={
                currentUsageVal >= 100
                  ? 'destructive'
                  : currentUsageVal >= 70
                  ? 'destructive'
                  : currentUsageVal >= 50
                  ? 'warning'
                  : 'success'
              }
              size="md"
              dot
            >
              {currentUsageVal >= 100
                ? '100% SATURATED'
                : currentUsageVal >= 70
                ? '70% CRITICAL BREACH'
                : currentUsageVal >= 50
                ? '50% ELEVATED WARNING'
                : 'NORMAL / HEALTHY'}
            </Badge>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-6 md:grid-cols-3 md:items-center border-t border-border/60 pt-5">
          {/* Main Utilization Figure */}
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground font-medium">Utilization Value</span>
            <div className="flex items-baseline gap-2">
              <span className="font-heading text-4xl font-extrabold tracking-tight text-foreground">
                {currentUsageVal > 0 ? `${currentUsageVal.toFixed(1)}%` : '0.0%'}
              </span>
              {peakUsageVal > 0 && (
                <span className="text-xs font-mono text-muted-foreground">
                  (Peak: {peakUsageVal.toFixed(1)}%)
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {data?.data_source || 'Live telemetry via /api/metrics & timestamp-filtered latest 5 recordings.'}
            </p>
          </div>

          {/* Visual Progress Bar with Threshold Markers */}
          <div className="space-y-2 md:col-span-2">
            <div className="flex justify-between text-xs font-medium">
              <span className="text-foreground">System Compute Headroom</span>
              <span className="font-mono text-muted-foreground">
                {(Math.max(100 - currentUsageVal, 0)).toFixed(1)}% Headroom Available
              </span>
            </div>
            <div className="relative h-3 w-full rounded-full bg-muted/60 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  currentUsageVal >= 50
                    ? 'bg-gradient-to-r from-[#00AAE7] to-[#8B0000]'
                    : 'bg-[#00AAE7]'
                }`}
                style={{ width: `${Math.min(Math.max(currentUsageVal, 0), 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-[11px] font-mono text-muted-foreground">
              <span>0% Baseline</span>
              <span>50% Warning</span>
              <span>70% Critical</span>
              <span>100% Saturation</span>
            </div>
          </div>
        </div>
      </div>

      {/* Email Alert Dispatch Notification */}
      {/* <div className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--status-success-border)] bg-[var(--status-success-bg)] p-3 text-xs text-[var(--status-success-text)]">
        <div className="flex items-center gap-2.5">
          <Mail className="h-4 w-4 shrink-0 text-[var(--primary)]" />
          <div>
            <span className="font-semibold">Nodemailer Alert Dispatched: </span>
            <span>Single consolidated alert sent for highest limit (<strong>{highestThreshold}</strong>) to </span>
            <code className="font-mono font-bold text-foreground">
              {data?.alert_recipient || 'sirivennelanarava@gmail.com'}
            </code>
          </div>
        </div>
        <Badge variant="success" size="sm">DELIVERED</Badge>
      </div> */}

      {/* Detection & Diagnosis Block */}
      {/* {detection && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          
          <Card
            title="Stage 1 & 2: Detection & Diagnosis Findings"
            subtitle={`Status: ${detection.status} | Diagnosis: ${detection.diagnosis_status}`}
            action={
              <Badge variant={detection.severity === 'HIGH' ? 'destructive' : 'warning'} size="sm">
                {detection.severity} SEVERITY
              </Badge>
            }
          >
            <div className="space-y-4">
              <div>
                <span className="text-xs font-medium text-muted-foreground">Issue Summary:</span>
                <p className="mt-1 text-sm font-medium text-foreground">{detection.summary}</p>
              </div>

              <div>
                <span className="text-xs font-medium text-muted-foreground">Root Cause Analysis:</span>
                <p className="mt-1 text-xs text-foreground/90 leading-relaxed bg-muted/30 p-2.5 rounded-[var(--radius-sm)] border border-border">
                  {detection.root_cause}
                </p>
              </div>

              <div>
                <span className="text-xs font-medium text-muted-foreground">Explanation:</span>
                <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                  {detection.explanation}
                </p>
              </div>

              {detection.reasons && detection.reasons.length > 0 && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground">Observed Evidence:</span>
                  <ul className="mt-1.5 space-y-1 text-xs text-foreground/80 list-disc list-inside">
                    {detection.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              {detection.evidence && (
                <div className="rounded-[var(--radius-sm)] bg-muted/40 p-3 font-mono text-[11px] space-y-1">
                  <div className="font-semibold text-foreground">Measured Metrics Evidence:</div>
                  {Object.entries(detection.evidence).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-muted-foreground">
                      <span>{k}:</span>
                      <span className="text-foreground font-semibold">{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
         
          <Card
            title="Stage 3: Remediation Plan & FinOps Guardrails"
            subtitle={`Action Category: ${remediation?.action_category || 'RECOMMENDATION_ONLY'}`}
            action={
              <Badge variant="primary" size="sm">
                REMEDIATION DRAFTED
              </Badge>
            }
          >
            <div className="space-y-4">
              <div>
                <span className="text-xs font-medium text-muted-foreground">Action Required:</span>
                <RemediationList
                  text={remediation?.action_required || 'Enforce partition predicate pruning and reservation burst ceiling.'}
                  className="text-sm font-semibold"
                />
              </div>

              {remediation?.preventive_guardrail && (
                <div className="rounded-[var(--radius-md)] border border-[var(--primary)]/30 bg-[var(--primary-tint)] p-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--primary)]">
                    <ShieldCheck className="h-4 w-4" />
                    FinOps Preventive Guardrail:
                  </div>
                  <RemediationList text={remediation.preventive_guardrail} />
                </div>
              )}

              {remediation?.recommended_query && (
                <div>
                  <div className="flex items-center justify-between pb-1.5">
                    <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                      <FileCode className="h-3.5 w-3.5 text-[var(--primary)]" />
                      Optimized SQL Query Recommendation:
                    </span>
                    <button
                      onClick={() => handleCopyQuery(remediation.recommended_query!)}
                      className="flex items-center gap-1 text-[11px] text-[var(--primary)] hover:underline"
                    >
                      {copiedQuery ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      <span>{copiedQuery ? 'Copied' : 'Copy SQL'}</span>
                    </button>
                  </div>
                  <pre className="overflow-x-auto rounded-[var(--radius-md)] border border-border bg-[#0B1220] p-3 font-mono text-[11px] text-[#E7EBF3] scrollbar-thin">
                    <code>{remediation.recommended_query}</code>
                  </pre>
                </div>
              )}

              {remediation?.verification_result && (
                <div className="flex items-start gap-2 rounded-[var(--radius-sm)] bg-[var(--status-success-bg)] p-2.5 text-xs text-[var(--status-success-text)] border border-[var(--status-success-border)]">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-[var(--success)] mt-0.5" />
                  <div>
                    <span className="font-semibold">Dry-run Verification: </span>
                    {remediation.verification_result}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      )} */}

      {/* Deep Telemetry Analysis & Host Processes */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {data?.cpu_utilization_analysis && (
          <Card
            title="Telemetry Utilization Analysis"
            subtitle="Preprocessed summary of core utilization & queue depth"
            action={<Badge variant="primary" size="sm">ANALYSIS SYNTHESIS</Badge>}
          >
            <div className="rounded-[var(--radius-md)] border border-border bg-[#0B1220] p-3 text-[11px] font-mono text-[#E7EBF3] whitespace-pre-wrap leading-relaxed">
              <div className="flex items-center gap-1.5 pb-2 text-[var(--primary)] border-b border-white/10 mb-2">
                <Activity className="h-3.5 w-3.5" />
                <span className="font-semibold">CPU Metric Assessment Summary</span>
              </div>
              {data.cpu_utilization_analysis}
            </div>
          </Card>
        )}

        {data?.top_processes && data.top_processes.length > 0 && (
          <Card
            title="Highest CPU Processes"
            subtitle="Processes utilizing significant CPU slots & execution cycles"
            action={<Badge variant="warning" size="sm">TOP {data.top_processes.length} TASKS</Badge>}
          >
            <div className="space-y-2">
              {data.top_processes.map((proc, pIdx) => (
                <div
                  key={pIdx}
                  className="flex items-center justify-between rounded-[var(--radius-sm)] border border-border/80 bg-muted/20 p-2.5 text-xs font-mono"
                >
                  <div className="flex items-center gap-2">
                    <Server className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-semibold text-foreground">{proc.process_name || proc.name || 'Unknown'}</span>
                    <span className="text-[11px] text-muted-foreground">(PID: {proc.pid})</span>
                  </div>
                  <Badge variant={Number(proc.cpu_percent) > 30 ? 'destructive' : 'warning'} size="sm">
                    {proc.cpu_percent}% CPU
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Remediation Plans List if available */}
      {data?.remediation_plans && data.remediation_plans.length > 0 && (
        <Card
          title="Consolidated Remediation Plans"
          subtitle={`${data.remediation_plans.length} action plan(s) formulated for affected services`}
          action={<Badge variant="success" size="sm">PLANS ACTIVE</Badge>}
        >
          <div className="space-y-3">
            {data.remediation_plans.map((plan, planIdx) => (
              <div
                key={planIdx}
                className="rounded-[var(--radius-md)] border border-border bg-card p-4 shadow-[var(--shadow-resting)]"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-mono text-xs">
                    <span className="font-bold text-[var(--primary)]">{plan.plan_id || `PLAN-${planIdx + 1}`}</span>
                    <span className="text-muted-foreground">•</span>
                    <span className="font-semibold text-foreground">{plan.service_name || 'VM Service'}</span>
                  </div>
                  <Badge variant={plan.severity === 'CRITICAL' ? 'destructive' : 'warning'} size="sm">
                    {plan.severity || 'HIGH'}
                  </Badge>
                </div>
                {plan.root_cause && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    <strong className="text-foreground">Root Cause: </strong> {plan.root_cause}
                  </p>
                )}
                {plan.action_required && (
                  <div className="mt-2 rounded-[var(--radius-sm)] bg-muted/40 p-2.5 text-xs text-foreground">
                    <strong className="text-[var(--primary)]">Action:</strong>
                    <RemediationList text={plan.action_required} />
                  </div>
                )}
                {plan.preventive_guardrail && (
                  <div className="mt-2 text-xs text-[var(--status-success-text)] font-medium">
                    <span>🛡️ Guardrail:</span>
                    <RemediationList text={plan.preventive_guardrail} className="mt-0 text-[11px] text-[var(--status-success-text)]" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};
