import React, { useState } from 'react';
import {
  Activity,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  CheckCircle,
  XCircle,
  Terminal,
  AlertTriangle,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { RemediationList } from '../common/RemediationList';
import { RemediationReviewCard } from '../common/RemediationReviewCard';
import type { AgentAnalysisResponse } from '../../types';
import { apiService } from '../../api/service';

interface DiskScreenProps {
  data: AgentAnalysisResponse | null;
  isLoading: boolean;
  onRunAnalysis: () => void;
  lastUpdated?: string;
}

export const DiskScreen: React.FC<DiskScreenProps> = ({
  data,
  isLoading,
  onRunAnalysis,
  lastUpdated: _lastUpdated,
}) => {
  const [actionStatus, setActionStatus] = useState<{
    status: 'PENDING' | 'EXECUTING' | 'EXECUTED' | 'REJECTED' | 'FAILED';
    message?: string;
    command?: string;
    target?: string;
    actionType?: string;
    details?: Record<string, any>;
    timestamp?: string;
  }>({ status: 'PENDING' });

  const detection = data?.detection;
  const remediation = data?.remediation;

  const handleRemediationDecision = async (decision: 'APPROVE' | 'REJECT') => {
    setActionStatus({ status: decision === 'APPROVE' ? 'EXECUTING' : 'REJECTED' });
    try {
      const result = await apiService.submitRemediationDecision({
        action_id: `REMED-DISK-${Date.now()}`,
        decision,
        action_type: 'RESTART_SERVICE',
        target_identifier: 'systemd-journald',
        process_name: 'systemd-journald',
        operator_email: 'operator@dashboard',
        operator_note: 'Triggered from Storage HITL screen',
      });

      setActionStatus({
        status: result.status,
        message: result.message || (result.success ? 'Executed successfully on VM' : 'Execution failed'),
        command: result.command || 'sudo systemctl restart systemd-journald',
        target: 'systemd-journald',
        actionType: 'RESTART_SERVICE',
        details: result.details,
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (err: any) {
      setActionStatus({
        status: 'FAILED',
        message: err.message || 'SSH execution error',
      });
    }
  };

  const diskStats = data?.disk_stats;
  const evidence = data?.detection?.evidence as {
    used_gb?: number;
    free_gb?: number;
    total_gb?: number;
    percent?: number;
  } | undefined;

  const usagePercent = diskStats?.current_percent ?? evidence?.percent ?? data?.current_usage_percent ?? 0;
  const usedGb = diskStats?.used_gb ?? evidence?.used_gb;
  const freeGb = diskStats?.free_gb ?? evidence?.free_gb;
  const totalGb = diskStats?.total_gb ?? evidence?.total_gb;
  const hostname = data?.hostname || diskStats?.hostname || 'System Volume';

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          {/* <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warning" size="sm">
              STORAGE & I/O AGENT
            </Badge>
            <span className="text-xs font-mono text-muted-foreground">/api/disk/analyze</span>
            {lastUpdated && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--success)] border border-[var(--success)]/20">
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)]"></span>
                Cached: {lastUpdated}
              </span>
            )}
          </div> */}
          {/* <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            Disk Utilization  Agent
          </h2> */}
          {/* <p className="text-xs text-muted-foreground">
            Monitors system storage volume utilization, audits capacity thresholds, and triggers automated retention actions.
          </p> */}
        </div>

        <button
          onClick={onRunAnalysis}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[var(--primary-hover)] disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Rerunning Disk Agent...' : 'Rerun Disk Agent'}</span>
        </button>
      </div>

      {/* Storage Meter */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-[var(--primary)]" />
              <span className="text-xs font-semibold text-foreground">Storage Volume ({hostname})</span>
            </div>
            <Badge variant={usagePercent >= 70 ? 'destructive' : usagePercent >= 50 ? 'warning' : 'success'} size="sm">
              {usagePercent}% USED
            </Badge>
          </div>

          <div className="mt-4">
            <div className="flex justify-between text-xs font-mono">
              <span className="text-muted-foreground">Used: {usedGb !== undefined ? `${usedGb} GB` : 'N/A'}</span>
              <span className="text-muted-foreground">Available: {freeGb !== undefined ? `${freeGb} GB` : 'N/A'}</span>
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
              <span>Safe Zone (≤50%)</span>
              <span>Warning Limit (60-70%)</span>
              <span>{totalGb !== undefined ? `${totalGb} GB` : '100%'}</span>
            </div>
          </div>
        </div>

        {/* <div className="rounded-[var(--radius-lg)] border border-border bg-card p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Log Directory Cache</span>
            <Archive className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="mt-2 font-heading text-2xl font-bold text-foreground">
            38 Snapshots
          </div>
          <p className="mt-1 text-xs text-muted-foreground">In logs/system_metrics_*.json</p>
          <button
            onClick={handleSimulateCleanup}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-muted/40 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
          >
            <FolderMinus className="h-3.5 w-3.5 text-[var(--primary)]" />
            <span>{cleaned ? 'Purged 14 Old Logs!' : 'Auto-Purge Expired Logs'}</span>
          </button>
        </div> */}
      </div>

      {/* Threshold notification */}
      {/* <div className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--status-info-border)] bg-[var(--status-info-bg)] p-3 text-xs text-[var(--status-info-text)]">
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 shrink-0 text-[var(--info)]" />
          <span>
            Disk Alert: Exceeded <strong>50% threshold</strong> ({usagePercent}%). Email alert recorded for <strong>sirivennelanarava@gmail.com</strong>.
          </span>
        </div>
        <Badge variant="info" size="sm">CONFIRMED</Badge>
      </div> */}

      {/* Detection & Remediation Blocks */}
      {detection && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card
            title="Storage Telemetry Diagnosis"
            subtitle={`Diagnosis Status: ${detection.diagnosis_status}`}
            action={<Badge variant="warning" size="sm">{detection.severity} SEVERITY</Badge>}
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
            </div>
          </Card>

          <Card
            title="Remediation Plan"
            subtitle="Auto-Fix Lifecycle Action"
            action={<Badge variant="success" size="sm">AUTO_FIX READY</Badge>}
          >
            <div className="space-y-4 text-xs">
              {remediation?.action_required && (
                <div>
                  <span className="font-semibold text-muted-foreground">Action Required:</span>
                  <RemediationList text={remediation.action_required} className="text-sm font-medium" />
                </div>
              )}

              {remediation?.preventive_guardrail && (
                <div className="rounded-[var(--radius-md)] border border-[var(--primary)]/30 bg-[var(--primary-tint)] p-3">
                  <div className="flex items-center gap-1.5 font-semibold text-[var(--primary)]">
                    <ShieldCheck className="h-4 w-4" />
                    Storage Policy Guardrail:
                  </div>
                  <RemediationList text={remediation.preventive_guardrail} />
                </div>
              )}

              {actionStatus.status === 'EXECUTED' ? (
                <div className="mt-3">
                  <RemediationReviewCard
                    actionId="REMED-DISK"
                    actionType={actionStatus.actionType || 'RESTART_SERVICE'}
                    target={actionStatus.target || 'systemd-journald'}
                    command={actionStatus.command || 'sudo systemctl restart systemd-journald'}
                    message={actionStatus.message}
                    details={actionStatus.details}
                    timestamp={actionStatus.timestamp}
                    onRerunAnalysis={onRunAnalysis}
                    onReset={() => setActionStatus({ status: 'PENDING' })}
                  />
                </div>
              ) : (
                <>
                  {/* Proposed SSH Command Preview */}
                  <div className="mt-3 rounded-[var(--radius-sm)] border border-[#1E293B] bg-[#090D16] p-3 text-xs font-mono shadow-inner">
                    <div className="flex items-center justify-between pb-1.5 border-b border-white/5 mb-2">
                      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400">
                        <Terminal className="h-3.5 w-3.5" /> Proposed SSH Command (on 20.15.164.79)
                      </span>
                      <span className="text-[10px] text-muted-foreground uppercase">
                        Target: Service systemd-journald
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[#38BDF8] select-all bg-black/40 px-2.5 py-1.5 rounded border border-white/5 overflow-x-auto">
                      <span className="text-muted-foreground select-none">$</span>
                      <code className="font-bold">sudo systemctl restart systemd-journald</code>
                    </div>
                  </div>

                  {/* Human-in-the-Loop Action Controls */}
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                        <Terminal className="h-3 w-3 text-primary" /> HITL Gate:
                      </span>
                      {actionStatus.status === 'REJECTED' && (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground">
                          <XCircle className="h-3.5 w-3.5" /> Rejected by Operator
                        </span>
                      )}
                      {actionStatus.status === 'FAILED' && (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold text-destructive">
                          <AlertTriangle className="h-3.5 w-3.5" /> Failed
                        </span>
                      )}
                      {actionStatus.status === 'PENDING' && (
                        <span className="text-xs text-amber-500 font-medium">Approval Required</span>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      {actionStatus.status !== 'REJECTED' && (
                        <>
                          <button
                            type="button"
                            onClick={() => handleRemediationDecision('APPROVE')}
                            disabled={actionStatus.status === 'EXECUTING'}
                            className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--primary)] px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
                          >
                            {actionStatus.status === 'EXECUTING' ? (
                              <>
                                <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Running over SSH...
                              </>
                            ) : (
                              <>
                                <CheckCircle className="h-3.5 w-3.5" /> Approve & Run via SSH
                              </>
                            )}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemediationDecision('REJECT')}
                            className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/50 cursor-pointer"
                          >
                            <XCircle className="h-3.5 w-3.5" /> Reject
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {actionStatus.status === 'FAILED' && actionStatus.message && (
                    <p className="mt-2 text-[11px] text-destructive bg-destructive/10 p-2 rounded font-mono">
                      {actionStatus.message}
                    </p>
                  )}
                </>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Disk Utilization Analysis */}
      {data?.disk_utilization_analysis && (
        <Card
          title="Disk Telemetry Assessment"
          subtitle="Storage accumulation dynamics & partition forecast"
          action={<Badge variant="warning" size="sm">ANALYSIS TEXT</Badge>}
        >
          <div className=" top-0 sticky max-h-[350px] overflow-y-auto rounded-[var(--radius-md)] border border-border bg-[#0B1220] p-3 text-[11px] font-mono text-[#E7EBF3] whitespace-pre-wrap leading-relaxed">
            <div className="flex items-center gap-1.5 pb-2 text-[var(--primary)] border-b border-white/10 mb-2">
              <Activity className="h-3.5 w-3.5" />
              <span className="font-semibold">Storage Space Diagnostics</span>
            </div>
            {data.disk_utilization_analysis}
          </div>
        </Card>
      )}
    </div>
  );
};
