import React from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Cpu,
  ExternalLink,
  HardDrive,
  Layers,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import type {
  AgentAnalysisResponse,
  EmailAlertsResponse,
  NavigationTab,
} from '../../types';

interface OverviewScreenProps {
  onNavigate: (tab: NavigationTab) => void;
  cpuData: AgentAnalysisResponse | null;
  diskData: AgentAnalysisResponse | null;
  memoryData: AgentAnalysisResponse | null;
  alertsData: EmailAlertsResponse | null;
  isLoadingAll: boolean;
  isCpuLoading: boolean;
  isDiskLoading: boolean;
  isMemoryLoading: boolean;
  onRerunAll: () => void;
  onRerunCpu: () => void;
  onRerunDisk: () => void;
  onRerunMemory: () => void;
  lastUpdated: {
    cpu?: string;
    disk?: string;
    memory?: string;
    all?: string;
  };
  onIngestMetrics?: () => void;
  isIngesting?: boolean;
}

export const OverviewScreen: React.FC<OverviewScreenProps> = ({
  onNavigate,
  cpuData,
  diskData,
  memoryData,
  alertsData,
  isLoadingAll,
  isCpuLoading,
  isDiskLoading,
  isMemoryLoading,
  onRerunAll,
  onRerunCpu,
  onRerunDisk,
  onRerunMemory,
  lastUpdated,
  onIngestMetrics: _onIngestMetrics,
  isIngesting: _isIngesting = false,
}) => {
  // Extract CPU Metrics
  const cpuCurrent = cpuData?.current_usage_percent ?? 0;
  const cpuPeak = cpuData?.peak_usage_percent ?? cpuCurrent;
  const cpuThreshold =
    cpuData?.highest_threshold_exceeded ||
    (cpuData?.highest_threshold_crossed ? `${cpuData.highest_threshold_crossed}%` : null);
  const cpuDetection = cpuData?.detection;

  // Extract Disk Metrics
  const diskStats = diskData?.disk_stats;
  const diskEvidence = diskData?.detection?.evidence as {
    used_gb?: number;
    free_gb?: number;
    total_gb?: number;
    percent?: number;
  } | undefined;
  const diskCurrent = diskData?.current_usage_percent ?? diskStats?.current_percent ?? (diskEvidence?.percent ?? 0);
  const diskUsedGb = diskStats?.used_gb ?? diskEvidence?.used_gb ?? 0;
  const diskTotalGb = diskStats?.total_gb ?? diskEvidence?.total_gb ?? 0;
  const diskThreshold =
    diskData?.highest_threshold_exceeded ||
    (diskData?.highest_threshold_crossed ? `${diskData.highest_threshold_crossed}%` : null);
  const diskDetection = diskData?.detection;

  // Extract Memory Metrics
  const memEvidence = memoryData?.detection?.evidence as {
    used_gb?: number;
    free_gb?: number;
    total_gb?: number;
    percent?: number;
  } | undefined;
  const memCurrent = memoryData?.current_usage_percent ?? (memEvidence?.percent ?? 0);
  const memUsedGb = memoryData?.memory_stats?.used_gb ?? (memEvidence?.used_gb ?? 0);
  const memTotalGb = memoryData?.memory_stats?.total_gb ?? (memEvidence?.total_gb ?? 0);
  const memThreshold =
    memoryData?.highest_threshold_exceeded ||
    (memoryData?.highest_threshold_crossed ? `${memoryData.highest_threshold_crossed}%` : null);
  const memDetection = memoryData?.detection;

  // Total alert count
  const alertCount = alertsData?.total_alerts ?? (alertsData?.alerts ? alertsData.alerts.length : 0);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Top Banner with Master Rerun All Agents Control */}
      <div className="relative overflow-hidden rounded-[var(--radius-xl)] border border-border bg-gradient-to-r from-card via-card to-[var(--primary-tint)] p-6 shadow-[var(--shadow-resting)]">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-center">
          <div className="space-y-1.5 max-w-3xl">
            {/* <div className="flex flex-wrap items-center gap-2">
              <Badge variant={systemStatusColor} dot size="sm">
                SYSTEM STATUS: {systemStatus}
              </Badge>
              <span className="font-mono text-xs text-muted-foreground flex items-center gap-1.5">
                <Server className="h-3 w-3 text-muted-foreground" />
                Backend: localhost:8000
              </span> 
              {lastUpdated.all && (
                <span className="inline-flex items-center gap-1 rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-[11px] font-medium text-[var(--success)] border border-[var(--success)]/20">
                  <Clock className="h-3 w-3" />
                  All Caches Synced: {lastUpdated.all}
                </span>
              )}
            </div> */}
            <h2 className="font-heading text-2xl font-bold tracking-tight text-foreground">
              Multi-Agent Telemetry & Infrastructure Health Overview
            </h2>
            <p className="text-xs text-muted-foreground leading-relaxed">
              All 3 autonomous monitoring agents (CPU, Disk, Memory) ran and cached upon launch. Review detection summaries, threshold breaches, and root-cause remediation plans below, or rerun individual or all agents on demand.
            </p>
          </div>

          {/* Master Rerun All Agents Action Buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={onRerunAll}
              disabled={isLoadingAll}
              data-slot="button"
              className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] px-4 py-2.5 text-xs font-bold text-white shadow-md transition-all hover:bg-[var(--primary-hover)] hover:shadow-lg disabled:opacity-50"
              title="Executes CPU Agent, Disk Agent, and Memory Agent concurrently and refreshes all cached telemetry"
            >
              <RefreshCw className={`h-4 w-4 ${isLoadingAll ? 'animate-spin' : ''}`} />
              <span>{isLoadingAll ? 'Rerunning All Agents...' : 'Rerun All Agents'}</span>
            </button>

            {/* {onIngestMetrics && (
              <button
                onClick={onIngestMetrics}
                disabled={isIngesting}
                className="flex items-center gap-1.5 rounded-[var(--radius-md)] border border-border bg-card/80 px-3.5 py-2 text-xs font-semibold text-foreground transition-all hover:bg-muted disabled:opacity-50"
              >
                <Zap className={`h-3.5 w-3.5 text-[var(--primary)] ${isIngesting ? 'animate-bounce' : ''}`} />
                <span>{isIngesting ? 'Ingesting...' : 'Ingest Live Telemetry'}</span>
              </button>
            )} */}
          </div>
        </div>
      </div>

      {/* 4 Interactive KPI Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* CPU KPI Card */}
        <div
          onClick={() => onNavigate('cpu')}
          className="group cursor-pointer rounded-[var(--radius-lg)] border border-border bg-card p-5 shadow-[var(--shadow-resting)] transition-all hover:-translate-y-0.5 hover:border-[var(--primary)]/50 hover:shadow-[var(--shadow-raised)]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">CPU Utilization</span>
            <div className="rounded-[var(--radius-md)] bg-muted/40 p-2 text-foreground group-hover:bg-[var(--primary-tint)] group-hover:text-[var(--primary)] transition-colors">
              <Cpu className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold tracking-tight text-foreground">
              {cpuCurrent}%
            </span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground truncate">
            Peak {cpuPeak}% · Slot burn on worker-node-04b
          </p>
          <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
            <span>Cache: {lastUpdated.cpu || 'None'}</span>
            <span className="font-medium text-[var(--primary)] group-hover:underline flex items-center gap-0.5">
              Open Agent <ArrowRight className="h-3 w-3" />
            </span>
          </div>
        </div>

        {/* Disk KPI Card */}
        <div
          onClick={() => onNavigate('disk')}
          className="group cursor-pointer rounded-[var(--radius-lg)] border border-border bg-card p-5 shadow-[var(--shadow-resting)] transition-all hover:-translate-y-0.5 hover:border-[var(--primary)]/50 hover:shadow-[var(--shadow-raised)]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Disk Utilization</span>
            <div className="rounded-[var(--radius-md)] bg-muted/40 p-2 text-foreground group-hover:bg-[var(--primary-tint)] group-hover:text-[var(--primary)] transition-colors">
              <HardDrive className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold tracking-tight text-foreground">
              {diskCurrent}%
            </span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground truncate">
            {diskUsedGb} GB used of {diskTotalGb} GB
          </p>
          <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
            <span>Cache: {lastUpdated.disk || 'None'}</span>
            <span className="font-medium text-[var(--primary)] group-hover:underline flex items-center gap-0.5">
              Open Agent <ArrowRight className="h-3 w-3" />
            </span>
          </div>
        </div>

        {/* Memory KPI Card */}
        <div
          onClick={() => onNavigate('memory')}
          className="group cursor-pointer rounded-[var(--radius-lg)] border border-border bg-card p-5 shadow-[var(--shadow-resting)] transition-all hover:-translate-y-0.5 hover:border-[var(--primary)]/50 hover:shadow-[var(--shadow-raised)]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">RAM Utilization</span>
            <div className="rounded-[var(--radius-md)] bg-muted/40 p-2 text-foreground group-hover:bg-[var(--primary-tint)] group-hover:text-[var(--primary)] transition-colors">
              <Layers className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold tracking-tight text-foreground">
              {memCurrent}%
            </span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground truncate">
            {memUsedGb} GB used of {memTotalGb} GB
          </p>
          <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
            <span>Cache: {lastUpdated.memory || 'None'}</span>
            <span className="font-medium text-[var(--primary)] group-hover:underline flex items-center gap-0.5">
              Open Agent <ArrowRight className="h-3 w-3" />
            </span>
          </div>
        </div>

        {/* Threshold Alerts KPI Card */}
        <div
          onClick={() => onNavigate('alerts')}
          className="group cursor-pointer rounded-[var(--radius-lg)] border border-border bg-card p-5 shadow-[var(--shadow-resting)] transition-all hover:-translate-y-0.5 hover:border-[var(--primary)]/50 hover:shadow-[var(--shadow-raised)]"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Threshold Email Alerts</span>
            <div className="rounded-[var(--radius-md)] bg-muted/40 p-2 text-foreground group-hover:bg-[var(--primary-tint)] group-hover:text-[var(--primary)] transition-colors">
              <AlertTriangle className="h-4 w-4 text-[var(--destructive)]" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-heading text-2xl font-bold tracking-tight text-foreground">
              {alertCount} Alerts
            </span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground truncate">
            Audited via Nodemailer pipeline
          </p>
          <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
            <span>Operations Log</span>
            <span className="font-medium text-[var(--primary)] group-hover:underline flex items-center gap-0.5">
              View Log <ArrowRight className="h-3 w-3" />
            </span>
          </div>
        </div>
      </div>

      {/* 3 Core Agent Deep-Dive Cards (CPU, Disk, Memory) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-lg font-bold text-foreground flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-[var(--primary)]" />
            Agent Findings & Diagnosis
          </h3>
          {/* <span className="text-xs text-muted-foreground font-mono">
            Cached telemetry state (re-runs on button trigger)
          </span> */}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Card 1: CPU Agent Card */}
          <Card
            title="1. CPU Agent"
            subtitle="Pipeline: Detection ➜ Diagnosis ➜ Remediation"
            action={
              <Badge variant="destructive" size="sm">
                {cpuThreshold} LIMIT
              </Badge>
            }
            footer={
              <div className="flex items-center justify-between w-full pt-2 border-t border-border/40">
                <div className="flex items-center gap-2">
                  <button
                    onClick={onRerunCpu}
                    disabled={isCpuLoading}
                    className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1 text-xs font-semibold text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                    title="Rerun CPU Agent"
                  >
                    <RefreshCw className={`h-3 w-3 ${isCpuLoading ? 'animate-spin text-[var(--primary)]' : ''}`} />
                    <span>{isCpuLoading ? 'Rerunning...' : 'Rerun CPU Agent'}</span>
                  </button>
                  <button
                    onClick={() => onNavigate('cpu')}
                    className="flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--primary)] px-2.5 py-1 text-xs font-semibold text-white hover:bg-[var(--primary-hover)] transition-colors"
                  >
                    <span>Details</span>
                    <ExternalLink className="h-3 w-3" />
                  </button>
                </div>
              </div>
            }
          >
            <div className="space-y-4">
              {/* Progress gauge */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium text-foreground">Current Slot Utilization</span>
                  <span
                    className="font-mono font-bold"
                    style={{ color: cpuCurrent >= 50 ? '#8B0000' : '#00AAE7' }}
                  >
                    {cpuCurrent}% (Peak {cpuPeak}%)
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      cpuCurrent >= 50
                        ? 'bg-gradient-to-r from-[#00AAE7] to-[#8B0000]'
                        : 'bg-[#00AAE7]'
                    }`}
                    style={{ width: `${Math.min(cpuCurrent, 100)}%` }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-[10px] text-muted-foreground font-mono">
                  <span>0%</span>
                  <span>50%</span>
                  <span>70%</span>
                  <span>100%</span>
                </div>
              </div>

              {/* What Agent Detected */}
              {cpuDetection?.summary && (
                <div className="rounded-[var(--radius-md)] border border-border/80 bg-muted/20 p-3 space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)]">
                    Issue Detected
                  </span>
                  <p className="text-xs text-foreground font-medium leading-relaxed">
                    {cpuDetection?.summary}
                  </p>
                </div>
              )}

              {/* Root Cause */}
              {cpuDetection?.root_cause && (
              <div className="space-y-1 text-xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Root Cause
                </span>
                <p className="text-muted-foreground leading-relaxed">
                  {cpuDetection?.root_cause}
                </p>
              </div>
              )}

              {/* Remediation Action */}
              {/* {cpuRemediation?.action_required &&(
              <div className="rounded-[var(--radius-md)] border border-border/60 bg-[var(--primary-tint)]/40 p-2.5 text-xs text-foreground space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)] flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  Recommended Action
                </span>
                <RemediationList text={cpuRemediation?.action_required} className="text-[11px] text-muted-foreground" />
              </div>
              )} */}
            </div>
          </Card>

          {/* Card 2: Disk Agent Card */}
          <Card
            title="2. Disk Agent"
            subtitle="Pipeline: Detection ➜ Diagnosis ➜ Remediation"
            action={
              <Badge variant="warning" size="sm">
                {diskThreshold} LIMIT
              </Badge>
            }
            footer={
              <div className="flex items-center justify-between w-full pt-2 border-t border-border/40">
                <div className="flex items-center gap-2">
                  <button
                    onClick={onRerunDisk}
                    disabled={isDiskLoading}
                    className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1 text-xs font-semibold text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                    title="Rerun Disk Agent"
                  >
                    <RefreshCw className={`h-3 w-3 ${isDiskLoading ? 'animate-spin text-[var(--primary)]' : ''}`} />
                    <span>{isDiskLoading ? 'Rerunning...' : 'Rerun Disk Agent'}</span>
                  </button>
                  <button
                    onClick={() => onNavigate('disk')}
                    className="flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--primary)] px-2.5 py-1 text-xs font-semibold text-white hover:bg-[var(--primary-hover)] transition-colors"
                  >
                    <span>Details</span>
                    <ExternalLink className="h-3 w-3" />
                  </button>
                </div>
              </div>
            }
          >
            <div className="space-y-4">
              {/* Progress gauge */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium text-foreground">Storage Volume Usage</span>
                  <span
                    className="font-mono font-bold"
                    style={{ color: diskCurrent >= 50 ? '#8B0000' : '#00AAE7' }}
                  >
                    {diskCurrent}% ({diskUsedGb} GB / {diskTotalGb} GB)
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      diskCurrent >= 50
                        ? 'bg-gradient-to-r from-[#00AAE7] to-[#8B0000]'
                        : 'bg-[#00AAE7]'
                    }`}
                    style={{ width: `${Math.min(diskCurrent, 100)}%` }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-[10px] text-muted-foreground font-mono">
                  <span>0%</span>
                  <span>50%</span>
                  <span>70%</span>
                  <span>100%</span>
                </div>
              </div>

              {/* What Agent Detected */}
              {diskDetection?.summary && (
                <div className="rounded-[var(--radius-md)] border border-border/80 bg-muted/20 p-3 space-y-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)]">
                    Issue Detected
                  </span>
                  <p className="text-xs text-foreground font-medium leading-relaxed">
                    {diskDetection?.summary}
                  </p>
                </div>
              )}

              {/* Root Cause */}
              {diskDetection?.root_cause && (
              <div className="space-y-1 text-xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Root Cause
                </span>
                <p className="text-muted-foreground leading-relaxed">
                  {diskDetection?.root_cause || 'Uncompressed raw metrics logs stored without TTL retention policy in /logs.'}
                </p>
              </div>
              )}

              {/* Remediation Action */}
              {/* {diskRemediation?.action_required && (
              <div className="rounded-[var(--radius-md)] border border-border/60 bg-[var(--primary-tint)]/40 p-2.5 text-xs text-foreground space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)] flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  Recommended Action
                </span>
                <RemediationList text={diskRemediation?.action_required} className="text-[11px] text-muted-foreground" />
              </div>
              )} */}
            </div>
          </Card>

          {/* Card 3: Memory Agent Card */}
          <Card
            title="3. Memory Agent"
            subtitle="Pipeline: Detection ➜ Diagnosis ➜ Remediation"
            action={
              <Badge variant="warning" size="sm">
                {memThreshold} LIMIT
              </Badge>
            }
            footer={
              <div className="flex items-center justify-between w-full pt-2 border-t border-border/40">
                <div className="flex items-center gap-2">
                  <button
                    onClick={onRerunMemory}
                    disabled={isMemoryLoading}
                    className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1 text-xs font-semibold text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                    title="Rerun Memory Agent"
                  >
                    <RefreshCw className={`h-3 w-3 ${isMemoryLoading ? 'animate-spin text-[var(--primary)]' : ''}`} />
                    <span>{isMemoryLoading ? 'Rerunning...' : 'Rerun Memory Agent'}</span>
                  </button>
                  <button
                    onClick={() => onNavigate('memory')}
                    className="flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--primary)] px-2.5 py-1 text-xs font-semibold text-white hover:bg-[var(--primary-hover)] transition-colors"
                  >
                    <span>Details</span>
                    <ExternalLink className="h-3 w-3" />
                  </button>
                </div>
              </div>
            }
          >
            <div className="space-y-4">
              {/* Progress gauge */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium text-foreground">Primary RAM Usage</span>
                  <span
                    className="font-mono font-bold"
                    style={{ color: memCurrent >= 50 ? '#8B0000' : '#00AAE7' }}
                  >
                    {memCurrent}% ({memUsedGb} GB / {memTotalGb} GB)
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      memCurrent >= 50
                        ? 'bg-gradient-to-r from-[#00AAE7] to-[#8B0000]'
                        : 'bg-[#00AAE7]'
                    }`}
                    style={{ width: `${Math.min(memCurrent, 100)}%` }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-[10px] text-muted-foreground font-mono">
                  <span>0%</span>
                  <span>50%</span>
                  <span>70%</span>
                  <span>100%</span>
                </div>
              </div>

              {/* What Agent Detected */}
              {memDetection?.summary && (
              <div className="rounded-[var(--radius-md)] border border-border/80 bg-muted/20 p-3 space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)]">
                  Issue Detected
                </span>
                <p className="text-xs text-foreground font-medium leading-relaxed">
                  {memDetection?.summary}
                </p>
              </div>
              )}

              {/* Root Cause */}
              {memDetection?.root_cause && (
              <div className="space-y-1 text-xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Root Cause
                </span>
                <p className="text-muted-foreground leading-relaxed">
                  {memDetection?.root_cause }
                </p>
              </div>
              )}

              {/* Remediation Action */}
              {/* {memRemediation?.action_required && (
              <div className="rounded-[var(--radius-md)] border border-border/60 bg-[var(--primary-tint)]/40 p-2.5 text-xs text-foreground space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--primary)] flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  Recommended Action
                </span>
                <RemediationList text={memRemediation?.action_required} className="text-[11px] text-muted-foreground" />
              </div>
              )} */}
            </div>
          </Card>
        </div>
      </div>

      {/* 
      <Card
        title="Side-by-Side Agent Status & Autonomous Diagnostics"
        subtitle="Current telemetry evaluation vs 50%, 70%, and 100% SLA thresholds"
        action={
          <span className="text-xs font-mono text-muted-foreground">
            FastAPI Endpoints Active
          </span>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-muted-foreground uppercase tracking-wider text-[10px]">
                <th className="py-2.5 px-3 font-semibold">Agent / Resource</th>
                <th className="py-2.5 px-3 font-semibold">Current %</th>
                <th className="py-2.5 px-3 font-semibold">Highest Limit Exceeded</th>
                <th className="py-2.5 px-3 font-semibold">Diagnosis Status</th>
                <th className="py-2.5 px-3 font-semibold">Remediation Action</th>
                <th className="py-2.5 px-3 font-semibold">Alert Recipient</th>
                <th className="py-2.5 px-3 font-semibold text-right">Rerun / Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              
              <tr className="hover:bg-muted/20 transition-colors">
                <td className="py-3 px-3">
                  <div className="flex items-center gap-2">
                    <div className="rounded bg-[var(--primary)]/10 p-1 text-[var(--primary)]">
                      <Cpu className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">CPU Agent</span>
                      <div className="text-[10px] text-muted-foreground font-mono">/api/cpu/analyze</div>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 font-mono font-bold text-[var(--status-error-text)]">
                  {cpuCurrent}%
                </td>
                <td className="py-3 px-3">
                  <Badge variant="destructive" size="sm">
                    {cpuThreshold} (Slot Contention)
                  </Badge>
                </td>
                <td className="py-3 px-3 text-muted-foreground">
                  <span className="inline-flex items-center gap-1 text-[var(--success)] font-medium">
                    <CheckCircle2 className="h-3 w-3" /> Confirmed
                  </span>
                </td>
                <td className="py-3 px-3 text-muted-foreground max-w-[200px] truncate" title={cpuRemediation?.action_required}>
                  {cpuRemediation?.action_required || 'Partition pruning & reservation cap'}
                </td>
                <td className="py-3 px-3 font-mono text-[11px] text-muted-foreground">
                  sirivennelanarava@gmail.com
                </td>
                <td className="py-3 px-3 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={onRerunCpu}
                      disabled={isCpuLoading}
                      className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
                      title="Rerun CPU Agent"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isCpuLoading ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      onClick={() => onNavigate('cpu')}
                      className="font-medium text-[var(--primary)] hover:underline ml-1"
                    >
                      View
                    </button>
                  </div>
                </td>
              </tr>

              
              <tr className="hover:bg-muted/20 transition-colors">
                <td className="py-3 px-3">
                  <div className="flex items-center gap-2">
                    <div className="rounded bg-amber-500/10 p-1 text-amber-500">
                      <HardDrive className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">Disk Agent</span>
                      <div className="text-[10px] text-muted-foreground font-mono">/api/disk/analyze</div>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 font-mono font-bold text-amber-500">
                  {diskCurrent}%
                </td>
                <td className="py-3 px-3">
                  <Badge variant="warning" size="sm">
                    {diskThreshold} (Volume Growth)
                  </Badge>
                </td>
                <td className="py-3 px-3 text-muted-foreground">
                  <span className="inline-flex items-center gap-1 text-[var(--success)] font-medium">
                    <CheckCircle2 className="h-3 w-3" /> Confirmed
                  </span>
                </td>
                <td className="py-3 px-3 text-muted-foreground max-w-[200px] truncate" title={diskRemediation?.action_required}>
                  {diskRemediation?.action_required || 'Gzip compression & 15GB FIFO limit'}
                </td>
                <td className="py-3 px-3 font-mono text-[11px] text-muted-foreground">
                  sirivennelanarava@gmail.com
                </td>
                <td className="py-3 px-3 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={onRerunDisk}
                      disabled={isDiskLoading}
                      className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
                      title="Rerun Disk Agent"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isDiskLoading ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      onClick={() => onNavigate('disk')}
                      className="font-medium text-[var(--primary)] hover:underline ml-1"
                    >
                      View
                    </button>
                  </div>
                </td>
              </tr>

            
              <tr className="hover:bg-muted/20 transition-colors">
                <td className="py-3 px-3">
                  <div className="flex items-center gap-2">
                    <div className="rounded bg-cyan-500/10 p-1 text-cyan-500">
                      <Layers className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">Memory Agent</span>
                      <div className="text-[10px] text-muted-foreground font-mono">/api/memory/analyze</div>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 font-mono font-bold text-cyan-500">
                  {memCurrent}%
                </td>
                <td className="py-3 px-3">
                  <Badge variant="warning" size="sm">
                    {memThreshold} (Heap Saturation)
                  </Badge>
                </td>
                <td className="py-3 px-3 text-muted-foreground">
                  <span className="inline-flex items-center gap-1 text-[var(--success)] font-medium">
                    <CheckCircle2 className="h-3 w-3" /> Confirmed
                  </span>
                </td>
                <td className="py-3 px-3 text-muted-foreground max-w-[200px] truncate" title={memRemediation?.action_required}>
                  {memRemediation?.action_required || 'Stream batch dataframes in 1000 items chunks'}
                </td>
                <td className="py-3 px-3 font-mono text-[11px] text-muted-foreground">
                  sirivennelanarava@gmail.com
                </td>
                <td className="py-3 px-3 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={onRerunMemory}
                      disabled={isMemoryLoading}
                      className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
                      title="Rerun Memory Agent"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isMemoryLoading ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      onClick={() => onNavigate('memory')}
                      className="font-medium text-[var(--primary)] hover:underline ml-1"
                    >
                      View
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card> */}

    </div>
  );
};
