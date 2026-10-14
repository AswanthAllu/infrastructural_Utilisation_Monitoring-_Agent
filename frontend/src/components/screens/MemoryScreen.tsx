import React from 'react';
import {
  Activity,
  Layers,
  RefreshCw,
  Server,
  ShieldCheck,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { RemediationList } from '../common/RemediationList';
import type { AgentAnalysisResponse } from '../../types';

interface MemoryScreenProps {
  data: AgentAnalysisResponse | null;
  isLoading: boolean;
  onRunAnalysis: () => void;
  lastUpdated?: string;
}

export const MemoryScreen: React.FC<MemoryScreenProps> = ({
  data,
  isLoading,
  onRunAnalysis,
  lastUpdated,
}) => {
  const detection = data?.detection;
  const remediation = data?.remediation;

  const memStats = data?.memory_stats;
  const evidence = detection?.evidence as {
    used_gb?: number;
    free_gb?: number;
    available_gb?: number;
    total_gb?: number;
    percent?: number;
  } | undefined;

  const usagePercent = memStats?.current_percent ?? evidence?.percent ?? data?.current_usage_percent ?? 0;
  const usedGb = memStats?.used_gb ?? evidence?.used_gb;
  const totalGb = memStats?.total_gb ?? evidence?.total_gb;
  const freeGb = memStats?.available_gb ?? evidence?.available_gb ?? evidence?.free_gb;
  const peakPercent = memStats?.peak_percent ?? data?.peak_usage_percent ?? usagePercent;

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info" size="sm">
              RAM AGENT PIPELINE
            </Badge>
            {lastUpdated && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--success)] border border-[var(--success)]/20">
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)]"></span>
                Cached: {lastUpdated}
              </span>
            )}
          </div>
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            Memory & RAM Allocation Management Agent
          </h2>
        </div>

        <button
          onClick={onRunAnalysis}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[var(--primary-hover)] disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Rerunning Memory Agent...' : 'Rerun Memory Agent'}</span>
        </button>
      </div>

      {/* Memory Utilization Meter & Gauges */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-[var(--primary)]" />
              <span className="text-xs font-semibold text-foreground">Primary RAM Pool Consumption</span>
            </div>
            <Badge variant={usagePercent > 70 ? 'destructive' : usagePercent > 50 ? 'warning' : 'success'} size="sm">
              {usagePercent}% IN USE
            </Badge>
          </div>

          <div className="mt-4">
            <div className="flex justify-between text-xs font-mono">
              <span className="text-muted-foreground">Used: {usedGb !== undefined ? `${usedGb} GB` : 'N/A'}</span>
              <span className="text-muted-foreground">Total: {totalGb !== undefined ? `${totalGb} GB` : 'N/A'}</span>
            </div>
            <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full transition-all duration-500 ${
                  usagePercent >= 50
                    ? 'bg-gradient-to-r from-[#00AAE7] to-[#8B0000]'
                    : 'bg-[#00AAE7]'
                }`}
                style={{ width: `${Math.min(usagePercent, 100)}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-muted-foreground font-mono">
              <span>0 GB</span>
              <span>Warning: {totalGb ? (totalGb * 0.5).toFixed(1) : '50%'} GB (50%)</span>
              <span>Critical: {totalGb ? (totalGb * 0.7).toFixed(1) : '70%'} GB (70%)</span>
              <span>{totalGb !== undefined ? `${totalGb} GB` : '100%'}</span>
            </div>
          </div>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-5">
          <span className="text-xs text-muted-foreground">Available / Free RAM</span>
          <div className="mt-2 font-heading text-2xl font-bold text-foreground">
            {freeGb !== undefined ? `${freeGb} GB` : 'N/A'}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Available capacity</p>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-5">
          <span className="text-xs text-muted-foreground">Peak RAM Utilization</span>
          <div className="mt-2 font-heading text-2xl font-bold text-foreground">
            {peakPercent}%
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Highest observed recording</p>
        </div>
      </div>

      {/* Email Alert Banner */}
      {/* <div className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-xs text-[var(--status-warning-text)]">
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 shrink-0 text-[var(--warning)]" />
          <span>
            Memory Alert Threshold: Exceeded <strong>70% limit</strong> ({usagePercent}%). Notification sent to <strong>sirivennelanarava@gmail.com</strong>.
          </span>
        </div>
        <Badge variant="warning" size="sm">ALERT SENT</Badge>
      </div> */}

      {/* Detection & Remediation Blocks */}
      {detection && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card
            title="Memory Anomaly Diagnosis"
            subtitle={`Status: ${detection.diagnosis_status || 'CONFIRMED'} (Confidence: ${Math.round((detection.confidence ?? 0.95) * 100)}%)`}
            action={
              <Badge variant="destructive" size="sm">
                HIGH MEMORY PRESSURE
              </Badge>
            }
          >
            <div className="space-y-3 text-xs">
              <div>
                <span className="font-semibold text-muted-foreground">Summary:</span>
                <p className="mt-1 text-sm font-medium text-foreground">{detection.summary}</p>
              </div>
              {detection.root_cause && (
              <div>
                <span className="font-semibold text-muted-foreground">Root Cause:</span>
                <p className="mt-1 text-xs text-foreground bg-muted/30 p-2.5 rounded-[var(--radius-sm)] border border-border">
                  {detection.root_cause}
                </p>
              </div>
              )}
              {detection.explanation && (
              <div>
                <span className="font-semibold text-muted-foreground">Explanation:</span>
                <p className="mt-1 text-muted-foreground leading-relaxed">{detection.explanation}</p>
              </div>
              )}
              {detection.reasons && (
                <div>
                  <span className="font-semibold text-muted-foreground">Reasons:</span>
                  <ul className="mt-1 list-disc list-inside space-y-1 text-foreground/80">
                    {detection.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Formulated Memory Remediation"
            subtitle="Streaming Chunk Mitigation & Guardrails"
            action={
              <Badge variant="primary" size="sm">
                REMEDIATION DRAFTED
              </Badge>
            }
          >
            <div className="space-y-4 text-xs">
              {remediation?.action_required && (
                <div>
                  <span className="font-semibold text-muted-foreground">Required Action:</span>
                    <RemediationList text={remediation.action_required} className="text-sm font-medium" />
                </div>
              )}

              {remediation?.preventive_guardrail && (
                <div className="rounded-[var(--radius-md)] border border-[var(--primary)]/30 bg-[var(--primary-tint)] p-3">
                  <div className="flex items-center gap-1.5 font-semibold text-[var(--primary)]">
                    <ShieldCheck className="h-4 w-4" />
                    Proactive Guardrail:
                  </div>
                    <RemediationList text={remediation.preventive_guardrail} />
                </div>
              )}

              {/* <div className="rounded-[var(--radius-sm)] bg-muted/40 p-3 space-y-2">
                <div className="font-semibold text-foreground">Mitigation Checklist:</div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />
                  <span>Migrate telemetry poller to yield generator iterators</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />
                  <span>Enforce Linux cgroup 4GB process memory hard ceiling</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />
                  <span>Invoke gc.collect() following large historical json parses</span>
                </div>
              </div> */}
            </div>
          </Card>
        </div>
      )}

      {/* Memory Utilization Analysis & Top Consuming Processes */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {data?.memory_utilization_analysis && (
          <Card
            title="RAM Telemetry Diagnosis"
            subtitle="Host JVM / Heap buffer and swap footprint assessment"
            action={<Badge variant="info" size="sm">TELEMETRY AUDIT</Badge>}
          >
            <div className="rounded-[var(--radius-md)] border border-border bg-[#0B1220] p-3 text-[11px] font-mono text-[#E7EBF3] whitespace-pre-wrap leading-relaxed">
              <div className="flex items-center gap-1.5 pb-2 text-[var(--primary)] border-b border-white/10 mb-2">
                <Activity className="h-3.5 w-3.5" />
                <span className="font-semibold">Memory Pressure Analysis</span>
              </div>
              {data.memory_utilization_analysis}
            </div>
          </Card>
        )}

        {data?.high_memory_processes && data.high_memory_processes.length > 0 && (
          <Card
            title="Highest RAM Processes"
            subtitle="Top processes ranked by Resident Set Size (RSS)"
            action={<Badge variant="warning" size="sm">TOP {data.high_memory_processes.length} PROCS</Badge>}
          >
            <div className="space-y-2">
              {data.high_memory_processes.map((proc, pIdx) => (
                <div
                  key={pIdx}
                  className="flex items-center justify-between rounded-[var(--radius-sm)] border border-border/80 bg-muted/20 p-2.5 text-xs font-mono"
                >
                  <div className="flex items-center gap-2">
                    <Server className="h-3.5 w-3.5 text-muted-foreground" />
                    <div>
                      <span className="font-semibold text-foreground">{proc.process_name || proc.name || 'Unknown'}</span>
                      <span className="ml-1 text-[11px] text-muted-foreground">(PID: {proc.pid})</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {proc.memory_rss_mb && (
                      <span className="text-[11px] text-muted-foreground">{proc.memory_rss_mb} MB</span>
                    )}
                    <Badge variant={Number(proc.memory_percent) > 30 ? 'destructive' : 'warning'} size="sm">
                      {proc.memory_percent}% RAM
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Services Breakdown if available */}
      {data?.high_memory_services && data.high_memory_services.length > 0 && (
        <Card
          title="Service Daemon Allocations"
          subtitle="Systemd services tracked by memory watcher"
          action={<Badge variant="neutral" size="sm">DAEMONS</Badge>}
        >
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {data.high_memory_services.map((svc, sIdx) => (
              <div
                key={sIdx}
                className="flex items-center justify-between rounded-[var(--radius-sm)] border border-border bg-card p-2.5 text-xs font-mono"
              >
                <div>
                  <span className="font-semibold text-foreground">{svc.service_name}</span>
                  <div className="text-[10px] text-[var(--success)]">{svc.active_state}</div>
                </div>
                <span className="font-bold text-[var(--primary)]">{svc.memory_percent}%</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};
