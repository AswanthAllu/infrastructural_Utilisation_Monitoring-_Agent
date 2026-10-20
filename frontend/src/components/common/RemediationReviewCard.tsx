import React, { useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  History,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { Badge } from './Badge';

export interface RemediationReviewCardProps {
  actionId?: string;
  actionType?: string;
  target?: string;
  command?: string;
  message?: string;
  details?: Record<string, any>;
  timestamp?: string;
  operator?: string;
  onRerunAnalysis?: () => void;
  onReset?: () => void;
  onViewHistory?: () => void;
}

export const RemediationReviewCard: React.FC<RemediationReviewCardProps> = ({
  actionId = 'HITL-ACTION',
  actionType = 'REMEDIATION',
  target,
  command,
  message,
  details,
  timestamp,
  operator = 'operator@dashboard',
  onRerunAnalysis,
  onReset,
  onViewHistory,
}) => {
  const [showFullOutput, setShowFullOutput] = useState(false);

  const execTime = timestamp || new Date().toLocaleString();
  const exitCode = details?.exit_code ?? 0;
  const stdout = details?.stdout || '';
  const stderr = details?.stderr || '';
  const executedCmd = command || details?.command || 'remediation command';

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--success)]/40 bg-[var(--success)]/5 p-5 shadow-sm transition-all animate-in fade-in zoom-in-95">
      {/* Review Header Banner */}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center border-b border-[var(--success)]/20 pb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--success)]/20 text-[var(--success)] ring-2 ring-[var(--success)]/30">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-heading text-sm font-bold text-foreground">
                Remediation Successfully Executed & Verified
              </h4>
              <Badge variant="success" size="sm">
                SUCCESS (Exit 0)
              </Badge>
              <span className="font-mono text-[10px] text-muted-foreground uppercase bg-muted/60 px-1.5 py-0.5 rounded">
                {actionId}
              </span>
            </div>
            <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5 font-mono">
              <ShieldCheck className="h-3 w-3 text-[var(--success)]" />
              <span>HITL Authorization Succeeded • Audited & Logged to VM</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onRerunAnalysis && (
            <button
              type="button"
              onClick={onRerunAnalysis}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--primary)] px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-[var(--primary-hover)] transition-all cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Re-run Diagnostics</span>
            </button>
          )}

          {onViewHistory && (
            <button
              type="button"
              onClick={onViewHistory}
              title="Inspect complete audit trail across all approved and rejected actions"
              className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--primary)]/40 bg-[var(--primary)]/10 px-2.5 py-1.5 text-xs font-semibold text-[var(--primary)] hover:bg-[var(--primary)]/20 transition-all cursor-pointer"
            >
              <History className="h-3 w-3" />
              <span>Audit History</span>
            </button>
          )}

          {onReset && (
            <button
              type="button"
              onClick={onReset}
              title="Unlock controls to evaluate another action"
              className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/50 cursor-pointer"
            >
              <RotateCcw className="h-3 w-3" />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* Review Attributes Grid */}
      <div className="mt-3.5 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs font-mono">
        <div className="rounded-[var(--radius-sm)] border border-border/60 bg-card p-2.5">
          <span className="text-[10px] text-muted-foreground uppercase block mb-1">Target Identifier</span>
          <span className="font-semibold text-foreground truncate block" title={target}>
            {target || 'system-target'}
          </span>
        </div>

        <div className="rounded-[var(--radius-sm)] border border-border/60 bg-card p-2.5">
          <span className="text-[10px] text-muted-foreground uppercase block mb-1">Action Type</span>
          <span className="font-semibold text-foreground truncate block">
            {actionType.replace('_', ' ')}
          </span>
        </div>

        <div className="rounded-[var(--radius-sm)] border border-border/60 bg-card p-2.5">
          <span className="text-[10px] text-muted-foreground uppercase block mb-1">Authorized By</span>
          <span className="font-semibold text-foreground truncate block" title={operator}>
            {operator}
          </span>
        </div>

        <div className="rounded-[var(--radius-sm)] border border-border/60 bg-card p-2.5">
          <span className="text-[10px] text-muted-foreground uppercase block mb-1">Execution Time</span>
          <span className="font-semibold text-foreground truncate block flex items-center gap-1">
            <Clock className="h-3 w-3 text-muted-foreground" />
            {execTime}
          </span>
        </div>
      </div>

      {/* Executed Shell Command Display */}
      <div className="mt-3 rounded-[var(--radius-sm)] border border-[#1E293B] bg-[#090D16] p-3 text-xs font-mono shadow-inner">
        <div className="flex items-center justify-between pb-1.5 border-b border-white/5 mb-2">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-400">
            <Terminal className="h-3.5 w-3.5" /> Executed SSH Shell Command (on 20.15.164.79)
          </span>
          <span className="text-[10px] text-muted-foreground uppercase">
            Exit Code: {exitCode}
          </span>
        </div>
        <div className="flex items-center gap-2 text-[#38BDF8] select-all bg-black/40 px-2.5 py-1.5 rounded border border-white/5 overflow-x-auto">
          <span className="text-muted-foreground select-none">$</span>
          <code className="font-bold">{executedCmd}</code>
        </div>
      </div>

      {/* Execution Telemetry / Output */}
      {message && (
        <div className="mt-2.5 rounded-[var(--radius-sm)] border border-[var(--success)]/30 bg-[var(--success)]/10 px-3 py-2 text-xs font-mono text-emerald-300">
          <span className="font-semibold">Status Output: </span>
          {message}
        </div>
      )}

      {/* Audit & Compliance Confirmation Footer */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--success)]/20 pt-2.5 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-2">
          <FileText className="h-3 w-3 text-[var(--success)]" />
          <span>Audit trail saved to <code className="text-foreground">logs/remediation_audit.log</code></span>
        </div>

        {(stdout || stderr) && (
          <button
            type="button"
            onClick={() => setShowFullOutput(!showFullOutput)}
            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground font-mono cursor-pointer"
          >
            <span>{showFullOutput ? 'Hide Terminal Telemetry' : 'Show Terminal Telemetry'}</span>
            {showFullOutput ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
        )}
      </div>

      {/* Expandable Raw Terminal Output */}
      {showFullOutput && (stdout || stderr) && (
        <div className="mt-2 rounded-[var(--radius-sm)] border border-border/80 bg-black/80 p-2.5 font-mono text-[11px] text-muted-foreground max-h-40 overflow-y-auto">
          {stdout && (
            <div>
              <span className="text-emerald-400 block pb-1">STDOUT:</span>
              <pre className="whitespace-pre-wrap">{stdout}</pre>
            </div>
          )}
          {stderr && (
            <div className="mt-2">
              <span className="text-amber-400 block pb-1">STDERR:</span>
              <pre className="whitespace-pre-wrap">{stderr}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
