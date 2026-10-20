import React, { useEffect, useState, useMemo } from 'react';
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Download,
  Filter,
  History,
  RefreshCw,
  Search,
  Terminal,
  Trash2,
  User,
  XCircle,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { apiService } from '../../api/service';
import type { RemediationAuditLog } from '../../types';

interface HistoryScreenProps {
  onNavigateToAgent?: (agent: string) => void;
}

export const HistoryScreen: React.FC<HistoryScreenProps> = () => {
  const [logs, setLogs] = useState<RemediationAuditLog[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'EXECUTED' | 'REJECTED' | 'FAILED'>('ALL');
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const [isClearing, setIsClearing] = useState<boolean>(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState<boolean>(false);

  const fetchLogs = async () => {
    setIsLoading(true);
    try {
      const res = await apiService.getRemediationAuditLogs(100);
      setLogs(res.logs || []);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleCopy = (text: string, type: 'id' | 'cmd') => {
    navigator.clipboard.writeText(text);
    if (type === 'id') {
      setCopiedId(text);
      setTimeout(() => setCopiedId(null), 2000);
    } else {
      setCopiedCmd(text);
      setTimeout(() => setCopiedCmd(null), 2000);
    }
  };

  const handleClearHistory = async () => {
    setIsClearing(true);
    try {
      await apiService.clearRemediationAuditLogs();
      setLogs([]);
      setConfirmClearOpen(false);
    } catch (err) {
      console.error('Failed to clear history:', err);
    } finally {
      setIsClearing(false);
    }
  };

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(logs, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `remediation_audit_history_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Metrics KPI calculations
  const totalCount = logs.length;
  const executedCount = logs.filter(
    (l) => l.status === 'EXECUTED' || l.status === 'SUCCESS' || (l.decision === 'APPROVED' && l.status !== 'FAILED')
  ).length;
  const rejectedCount = logs.filter(
    (l) => l.status === 'REJECTED' || l.decision === 'REJECTED'
  ).length;
  const failedCount = logs.filter(
    (l) => l.status === 'FAILED' && l.decision !== 'REJECTED'
  ).length;

  const distinctTypes = useMemo(() => {
    const types = new Set<string>();
    logs.forEach((l) => {
      if (l.action_type) types.add(l.action_type);
    });
    return Array.from(types);
  }, [logs]);

  // Filtered logs
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      // Status filter
      const isApprovedOrExec =
        log.status === 'EXECUTED' || log.status === 'SUCCESS' || (log.decision === 'APPROVED' && log.status !== 'FAILED');
      const isRej = log.status === 'REJECTED' || log.decision === 'REJECTED';
      const isFail = log.status === 'FAILED' && log.decision !== 'REJECTED';

      if (statusFilter === 'EXECUTED' && !isApprovedOrExec) return false;
      if (statusFilter === 'REJECTED' && !isRej) return false;
      if (statusFilter === 'FAILED' && !isFail) return false;

      // Type filter
      if (typeFilter !== 'ALL' && log.action_type !== typeFilter) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchId = (log.action_id || '').toLowerCase().includes(q);
        const matchTarget = (log.target || '').toLowerCase().includes(q);
        const matchCmd = (log.command || '').toLowerCase().includes(q);
        const matchOp = (log.operator || '').toLowerCase().includes(q);
        const matchNote = (log.operator_note || '').toLowerCase().includes(q);
        const matchOut = (log.output || log.stdout || log.stderr || '').toLowerCase().includes(q);
        if (!matchId && !matchTarget && !matchCmd && !matchOp && !matchNote && !matchOut) {
          return false;
        }
      }

      return true;
    });
  }, [logs, statusFilter, typeFilter, searchQuery]);

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return {
        date: d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }),
        time: d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      };
    } catch {
      return { date: isoString, time: '' };
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--primary)]/10 text-[var(--primary)]">
              <History className="h-4 w-4" />
            </span>
            <span className="text-xs font-mono font-semibold uppercase tracking-wider text-[var(--primary)]">
              Audit Trail & Decision History
            </span>
          </div>
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            Remediation Action History
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Complete historical log of all Human-in-the-Loop approved executions, operator rejections, and remote SSH responses.
          </p>
        </div>

        {/* Global Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={fetchLogs}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/60 transition-colors cursor-pointer disabled:opacity-50"
            title="Reload latest records from audit log"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? 'Loading...' : 'Refresh'}</span>
          </button>

          <button
            type="button"
            onClick={handleExportJson}
            disabled={logs.length === 0}
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/60 transition-colors cursor-pointer disabled:opacity-50"
            title="Export all audit logs to JSON"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Export</span>
          </button>

          {confirmClearOpen ? (
            <div className="flex items-center gap-1.5 bg-rose-500/10 border border-rose-500/30 p-1 rounded-[var(--radius-md)]">
              <span className="text-[11px] text-rose-400 font-medium px-1">Clear all?</span>
              <button
                type="button"
                onClick={handleClearHistory}
                disabled={isClearing}
                className="rounded bg-rose-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-rose-700 cursor-pointer"
              >
                {isClearing ? 'Clearing...' : 'Yes, Clear'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmClearOpen(false)}
                className="rounded border border-border bg-card px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted cursor-pointer"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClearOpen(true)}
              disabled={logs.length === 0}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-rose-400 hover:border-rose-400/40 transition-colors cursor-pointer disabled:opacity-50"
              title="Clear all recorded history"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Clear History</span>
            </button>
          )}
        </div>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-[var(--radius-md)] border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>Total Logged</span>
            <History className="h-4 w-4 text-[var(--primary)]" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-foreground">{totalCount}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">HITL decision actions</div>
        </div>

        <div className="rounded-[var(--radius-md)] border border-emerald-500/20 bg-emerald-500/5 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-emerald-400">
            <span>Approved & Executed</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-emerald-400">{executedCount}</div>
          <div className="mt-1 text-[11px] text-emerald-500/80">
            {totalCount > 0 ? `${Math.round((executedCount / totalCount) * 100)}% approval rate` : '0%'}
          </div>
        </div>

        <div className="rounded-[var(--radius-md)] border border-amber-500/20 bg-amber-500/5 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-amber-400">
            <span>Rejected by Operator</span>
            <XCircle className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-amber-400">{rejectedCount}</div>
          <div className="mt-1 text-[11px] text-amber-500/80">Declined via HITL gate</div>
        </div>

        <div className="rounded-[var(--radius-md)] border border-rose-500/20 bg-rose-500/5 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-rose-400">
            <span>VM Failed</span>
            <AlertTriangle className="h-4 w-4 text-rose-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-rose-400">{failedCount}</div>
          <div className="mt-1 text-[11px] text-rose-500/80">SSH execution error</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 rounded-[var(--radius-md)] border border-border bg-card p-3 shadow-sm md:flex-row md:items-center md:justify-between">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by Action ID, target PID/service, command, operator, or error output..."
            className="w-full rounded-[var(--radius-sm)] border border-border bg-muted/20 pl-9 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-[var(--radius-sm)] border border-border bg-muted/30 p-1">
            <span className="text-[11px] text-muted-foreground px-1 font-medium flex items-center gap-1">
              <Filter className="h-3 w-3" /> Status:
            </span>
            {(['ALL', 'EXECUTED', 'REJECTED', 'FAILED'] as const).map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`rounded px-2 py-0.5 text-[11px] font-semibold transition-all cursor-pointer ${
                  statusFilter === st
                    ? st === 'EXECUTED'
                      ? 'bg-emerald-500 text-white shadow-sm'
                      : st === 'REJECTED'
                      ? 'bg-amber-500 text-white shadow-sm'
                      : st === 'FAILED'
                      ? 'bg-rose-500 text-white shadow-sm'
                      : 'bg-[var(--primary)] text-white shadow-sm'
                    : 'text-muted-foreground hover:bg-muted/60'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Action Type Dropdown Filter */}
          {distinctTypes.length > 0 && (
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)] cursor-pointer"
            >
              <option value="ALL">All Action Types</option>
              {distinctTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Audit History Records */}
      <Card
        title={`Audit Records (${filteredLogs.length} of ${totalCount})`}
        subtitle="Ordered by latest decision first. Click any record to inspect full SSH terminal response & telemetry details."
      >
        {filteredLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50 text-muted-foreground mb-3">
              <History className="h-6 w-6" />
            </div>
            <p className="text-sm font-semibold text-foreground">No remediation history records found</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              {searchQuery || statusFilter !== 'ALL' || typeFilter !== 'ALL'
                ? 'Try clearing your search query or adjusting your status filters.'
                : 'Approve or reject a remediation proposal on the CPU, Memory, or Disk agent screen to generate audit records.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredLogs.map((log, idx) => {
              const uniqueKey = `${log.action_id || 'LOG'}-${idx}-${log.timestamp}`;
              const isExpanded = expandedRow === uniqueKey;

              const isApproved =
                log.status === 'EXECUTED' ||
                log.status === 'SUCCESS' ||
                (log.decision === 'APPROVED' && log.status !== 'FAILED');
              const isRejected = log.status === 'REJECTED' || log.decision === 'REJECTED';
              const isFailed = log.status === 'FAILED' && log.decision !== 'REJECTED';

              const { date, time } = formatDate(log.timestamp);

              return (
                <div
                  key={uniqueKey}
                  className={`rounded-[var(--radius-md)] border transition-all ${
                    isExpanded
                      ? 'border-[var(--primary)] bg-[var(--primary)]/5 shadow-md'
                      : 'border-border/80 bg-card hover:border-border hover:bg-muted/20'
                  }`}
                >
                  {/* Card Header Summary */}
                  <div className="p-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex items-start gap-3">
                      {/* Status Icon */}
                      <div className="mt-0.5 shrink-0">
                        {isApproved && (
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <CheckCircle2 className="h-4 w-4" />
                          </div>
                        )}
                        {isRejected && (
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            <XCircle className="h-4 w-4" />
                          </div>
                        )}
                        {isFailed && (
                          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                            <AlertTriangle className="h-4 w-4" />
                          </div>
                        )}
                      </div>

                      {/* Main Title & Metadata */}
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          {/* Status Badge */}
                          {isApproved && (
                            <Badge variant="success" size="sm">
                              APPROVED & EXECUTED
                            </Badge>
                          )}
                          {isRejected && (
                            <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold uppercase bg-amber-500/15 text-amber-400 border border-amber-500/30">
                              REJECTED BY OPERATOR
                            </span>
                          )}
                          {isFailed && (
                            <Badge variant="destructive" size="sm">
                              EXECUTION FAILED
                            </Badge>
                          )}

                          {/* Action Type */}
                          <span className="font-mono text-[11px] text-muted-foreground uppercase bg-muted/50 px-2 py-0.5 rounded border border-border">
                            {log.action_type || 'COMMAND'}
                          </span>

                          {/* Action ID with copy */}
                          <div className="flex items-center gap-1 font-mono text-[11px] text-foreground bg-muted/40 px-2 py-0.5 rounded">
                            <span>{log.action_id}</span>
                            <button
                              type="button"
                              onClick={() => handleCopy(log.action_id, 'id')}
                              className="text-muted-foreground hover:text-foreground p-0.5"
                              title="Copy Action ID"
                            >
                              {copiedId === log.action_id ? (
                                <Check className="h-3 w-3 text-emerald-400" />
                              ) : (
                                <Copy className="h-3 w-3" />
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Target & Command preview */}
                        <div className="flex flex-wrap items-center gap-3 text-xs pt-0.5">
                          <span className="text-muted-foreground">
                            Target:{' '}
                            <strong className="text-foreground font-mono">
                              {log.target || 'System'}
                            </strong>
                          </span>
                          <span className="text-muted-foreground">•</span>
                          <span className="text-muted-foreground flex items-center gap-1">
                            <User className="h-3 w-3" />
                            <span>{log.operator || 'operator@dashboard'}</span>
                          </span>
                          <span className="text-muted-foreground">•</span>
                          <span className="text-muted-foreground flex items-center gap-1 font-mono text-[11px]">
                            <Clock className="h-3 w-3" />
                            <span>
                              {date} at {time}
                            </span>
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Right Action buttons */}
                    <div className="flex items-center gap-2 self-end lg:self-center">
                      <button
                        type="button"
                        onClick={() => setExpandedRow(isExpanded ? null : uniqueKey)}
                        className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted cursor-pointer transition-colors"
                      >
                        <span>{isExpanded ? 'Hide Details' : 'View Full Info'}</span>
                        {isExpanded ? (
                          <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Command Row Preview */}
                  <div className="px-4 pb-3">
                    <div className="flex items-center justify-between rounded border border-border/60 bg-[#090D16] px-3 py-1.5 text-xs font-mono text-[#38BDF8]">
                      <div className="flex items-center gap-2 overflow-x-auto select-all">
                        <span className="text-muted-foreground select-none">$</span>
                        <code className="font-semibold">{log.command}</code>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleCopy(log.command, 'cmd')}
                        className="ml-2 text-muted-foreground hover:text-white p-1"
                        title="Copy command"
                      >
                        {copiedCmd === log.command ? (
                          <Check className="h-3.5 w-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Full Info Drawer */}
                  {isExpanded && (
                    <div className="border-t border-border bg-muted/20 p-4 space-y-4 rounded-b-[var(--radius-md)] animate-fade-in">
                      {/* Operator Note / Justification */}
                      {log.operator_note && (
                        <div>
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                            Operator Justification / Rejection Note:
                          </span>
                          <p className="mt-1 text-xs text-foreground bg-card p-2.5 rounded border border-border">
                            {log.operator_note}
                          </p>
                        </div>
                      )}

                      {/* Execution Output or SSH Terminal Logs */}
                      <div>
                        <div className="flex items-center justify-between pb-1">
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                            <Terminal className="h-3.5 w-3.5 text-emerald-400" />
                            Remote VM Execution Output (Exit Code: {log.exit_code ?? (isApproved ? 0 : -1)})
                          </span>
                          <span className="text-[10px] font-mono text-muted-foreground">Host: 20.15.164.79</span>
                        </div>
                        <div className="rounded border border-[#1E293B] bg-[#050811] p-3 font-mono text-xs text-slate-200 overflow-x-auto max-h-48 scrollbar-thin">
                          {log.stderr && (
                            <div className="text-rose-400 mb-1 whitespace-pre-wrap">
                              {log.stderr}
                            </div>
                          )}
                          {log.stdout && (
                            <div className="text-emerald-300 whitespace-pre-wrap">
                              {log.stdout}
                            </div>
                          )}
                          {!log.stdout && !log.stderr && log.output && (
                            <div className="text-slate-300 whitespace-pre-wrap">
                              {log.output}
                            </div>
                          )}
                          {!log.stdout && !log.stderr && !log.output && (
                            <div className="text-muted-foreground italic">
                              Command executed cleanly with no stdout output (Exit Code: {log.exit_code ?? 0}).
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Technical Audit Metadata Grid */}
                      <div className="grid grid-cols-2 gap-3 text-xs bg-card p-3 rounded border border-border">
                        <div>
                          <span className="text-[10px] font-mono uppercase text-muted-foreground">Decision Gate</span>
                          <div className="font-semibold text-foreground">{log.decision || (isApproved ? 'APPROVED' : 'REJECTED')}</div>
                        </div>
                        <div>
                          <span className="text-[10px] font-mono uppercase text-muted-foreground">Execution Status</span>
                          <div className="font-semibold text-foreground">{log.status}</div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
};
