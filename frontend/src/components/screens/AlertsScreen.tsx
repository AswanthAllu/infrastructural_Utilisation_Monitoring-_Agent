import React, { useState, useEffect } from 'react';
import {
  Bell,
  CheckCircle2,
  Clock,
  Edit2,
  Mail,
  Plus,
  Power,
  RefreshCw,
  Search,
  ShieldAlert,
  Sliders,
  Trash2,
  X,
} from 'lucide-react';
import { Badge } from '../common/Badge';
import { apiService } from '../../api';
import type { AlertThresholdRule, EmailAlertRecord, EmailAlertsResponse } from '../../types';

interface AlertsScreenProps {
  data: EmailAlertsResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export const AlertsScreen: React.FC<AlertsScreenProps> = ({
  data,
  isLoading,
  onRefresh,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [thresholdFilter, setThresholdFilter] = useState('ALL');

  // Configurable threshold rules state
  const [rules, setRules] = useState<AlertThresholdRule[]>([]);
  const [isLoadingRules, setIsLoadingRules] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Inline Quick Creator / Editor state (No heavy modal)
  const [isInlineOpen, setIsInlineOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertThresholdRule | null>(null);
  const [formResource, setFormResource] = useState<'CPU' | 'RAM' | 'Disk' | 'ALL'>('CPU');
  const [formThreshold, setFormThreshold] = useState<number>(75);
  const [formSeverity, setFormSeverity] = useState<'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'>('HIGH');
  const [formRecipient, setFormRecipient] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);
  const [isSavingRule, setIsSavingRule] = useState(false);

  // Load configured threshold rules from backend
  const fetchRules = async () => {
    setIsLoadingRules(true);
    setRulesError(null);
    try {
      const res = await apiService.getThresholdRules();
      if (res.success) {
        setRules(res.rules || []);
      }
    } catch (err: any) {
      setRulesError(err.message || 'Failed to load configured threshold rules');
    } finally {
      setIsLoadingRules(false);
    }
  };

  useEffect(() => {
    fetchRules();
  }, []);

  const handleFullRefresh = async () => {
    onRefresh();
    await fetchRules();
  };

  // Open inline adder
  const handleOpenAddInline = () => {
    setEditingRule(null);
    setFormResource('CPU');
    setFormThreshold(75);
    setFormSeverity('HIGH');
    setFormRecipient('');
    setFormEnabled(true);
    setIsInlineOpen(true);
  };

  // Open inline editor for an existing rule
  const handleOpenEditInline = (rule: AlertThresholdRule) => {
    setEditingRule(rule);
    setFormResource((rule.resource as any) || 'CPU');
    setFormThreshold(rule.threshold_percent);
    setFormSeverity((rule.severity as any) || 'HIGH');
    setFormRecipient(rule.recipient || '');
    setFormEnabled(rule.enabled);
    setIsInlineOpen(true);
  };

  // Save (Create or Update) threshold rule
  const handleSaveRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formThreshold <= 0 || formThreshold > 100) {
      alert('Threshold percentage must be between 1 and 100.');
      return;
    }

    setIsSavingRule(true);
    try {
      if (editingRule) {
        await apiService.updateThresholdRule(editingRule.id, {
          resource: formResource,
          threshold_percent: formThreshold,
          severity: formSeverity,
          recipient: formRecipient,
          enabled: formEnabled,
        });
        setStatusMessage(`Updated ${formResource} ${formThreshold}% threshold rule.`);
      } else {
        await apiService.createThresholdRule({
          resource: formResource,
          threshold_percent: formThreshold,
          severity: formSeverity,
          recipient: formRecipient,
          enabled: formEnabled,
        });
        setStatusMessage(`Added new ${formResource} ${formThreshold}% threshold rule.`);
      }
      setIsInlineOpen(false);
      setEditingRule(null);
      await fetchRules();
      onRefresh();
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err: any) {
      alert(err.message || 'Failed to save threshold rule');
    } finally {
      setIsSavingRule(false);
    }
  };

  const handleToggleRule = async (ruleId: number) => {
    try {
      await apiService.toggleThresholdRule(ruleId);
      await fetchRules();
      onRefresh();
    } catch (err: any) {
      alert(err.message || 'Failed to toggle threshold rule');
    }
  };

  const handleDeleteRule = async (ruleId: number, desc: string) => {
    if (!window.confirm(`Delete the ${desc} threshold rule?`)) return;
    try {
      await apiService.deleteThresholdRule(ruleId);
      await fetchRules();
      onRefresh();
      setStatusMessage(`Deleted threshold rule.`);
      setTimeout(() => setStatusMessage(null), 4000);
    } catch (err: any) {
      alert(err.message || 'Failed to delete threshold rule');
    }
  };

  const rawAlerts: EmailAlertRecord[] = data?.alerts || [];

  // Sort alerts with latest/newest first
  const sortedAlerts = [...rawAlerts].sort((a, b) => {
    const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
    const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
    if (timeA !== timeB) return timeB - timeA;
    const idA = a.id ?? 0;
    const idB = b.id ?? 0;
    return idB - idA;
  });

  // Filter alerts by search term and threshold
  const filteredAlerts = sortedAlerts.filter((alert) => {
    const subject = alert.subject || '';
    const metricName = alert.metric_name || '';
    const recipient = alert.recipient || 'Unknown recipient';
    const thresholdLevel = (alert.threshold_level || '').replace('%', '').trim();
    const alertThreshold = alert.threshold ? alert.threshold.toString() : thresholdLevel;

    const matchesSearch =
      subject.toLowerCase().includes(searchTerm.toLowerCase()) ||
      metricName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      recipient.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesThreshold =
      thresholdFilter === 'ALL' ||
      alertThreshold === thresholdFilter ||
      (alert.threshold_level || '').includes(thresholdFilter);

    return matchesSearch && matchesThreshold;
  });

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-[var(--primary)]/10 text-[var(--primary)]">
              <Bell className="h-3.5 w-3.5" />
            </span>
            <span className="text-xs font-mono font-semibold uppercase tracking-wider text-[var(--primary)]">
              Alerts & Notification Dispatch
            </span>
          </div>
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            Threshold Alert Notifications
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Monitor real-time system alert dispatches and configure notification triggers with instant inline controls.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleFullRefresh}
            disabled={isLoading || isLoadingRules}
            className="flex items-center gap-1.5 rounded-[var(--radius-md)] border border-border bg-card px-3.5 py-1.5 text-xs font-semibold text-foreground shadow-sm transition-all hover:bg-muted/50 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading || isLoadingRules ? 'animate-spin' : ''}`} />
            <span>{isLoading || isLoadingRules ? 'Reloading...' : 'Refresh'}</span>
          </button>
        </div>
      </div>

      {/* Success / Status Banner */}
      {statusMessage && (
        <div className="flex items-center justify-between rounded-[var(--radius-md)] border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-xs font-medium text-emerald-400 animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{statusMessage}</span>
          </div>
          <button onClick={() => setStatusMessage(null)} className="cursor-pointer">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-[var(--radius-md)] border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>Total Dispatched</span>
            <ShieldAlert className="h-4 w-4 text-[var(--warning)]" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-foreground">
            {data?.total_alerts ?? sortedAlerts.length}
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">Latest alerts listed first</div>
        </div>

        <div className="rounded-[var(--radius-md)] border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>Active Threshold Rules</span>
            <Sliders className="h-4 w-4 text-[var(--primary)]" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-[var(--primary)]">
            {rules.filter((r) => r.enabled).length} of {rules.length} Active
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">Configured alert triggers</div>
        </div>

        <div className="rounded-[var(--radius-md)] border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>Primary Dispatch Mailbox</span>
            <Mail className="h-4 w-4 text-[var(--primary)]" />
          </div>
          <div className="mt-2 text-sm font-bold font-mono text-foreground truncate">
            {import.meta.env.VITE_DEFAULT_ALERT_EMAIL || 'Configured via SMTP'}
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">Default delivery receiver</div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* MINIMALIST THRESHOLD CHIPS & INLINE INSTANT CREATOR STRIP                */}
      {/* ========================================================================= */}
      <div className="rounded-[var(--radius-lg)] border border-border bg-card p-4 shadow-sm space-y-3">
        {/* Strip Header */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Sliders className="h-4 w-4 text-[var(--primary)]" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Alert Thresholds:
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">
              ({rules.filter((r) => r.enabled).length} active)
            </span>
          </div>

          {!isInlineOpen && (
            <button
              onClick={handleOpenAddInline}
              className="inline-flex items-center gap-1.5 self-start sm:self-auto rounded-full border border-[var(--primary)]/30 bg-[var(--primary)]/10 px-3 py-1 text-xs font-semibold text-[var(--primary)] hover:bg-[var(--primary)]/20 transition-all cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Add Threshold</span>
            </button>
          )}
        </div>

        {rulesError && (
          <div className="rounded-[var(--radius-sm)] bg-[var(--destructive)]/10 p-2.5 text-xs text-[var(--destructive)]">
            {rulesError}
          </div>
        )}

        {/* Minimalist Interactive Threshold Chips Bar */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {/* "All" Filter Chip */}
          <button
            onClick={() => setThresholdFilter('ALL')}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition-all cursor-pointer ${
              thresholdFilter === 'ALL'
                ? 'bg-foreground text-background shadow-xs'
                : 'border border-border bg-muted/30 text-muted-foreground hover:bg-muted/60'
            }`}
          >
            All Alerts ({sortedAlerts.length})
          </button>

          {/* Dynamic Rule Chips */}
          {rules.map((rule) => {
            const isSelected = thresholdFilter === String(rule.threshold_percent);
            const resColor =
              rule.resource === 'CPU'
                ? 'text-blue-500'
                : rule.resource === 'RAM'
                ? 'text-emerald-500'
                : rule.resource === 'Disk'
                ? 'text-amber-500'
                : 'text-purple-500';

            return (
              <div
                key={rule.id}
                className={`group inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-all ${
                  isSelected
                    ? 'border-[var(--primary)] bg-[var(--primary)]/15 text-[var(--primary)] ring-1 ring-[var(--primary)]/40 font-semibold shadow-xs'
                    : rule.enabled
                    ? 'border-border/80 bg-background text-foreground hover:border-border'
                    : 'border-border/40 bg-muted/20 text-muted-foreground opacity-60'
                }`}
              >
                {/* Click Chip to Filter Alerts */}
                <button
                  type="button"
                  onClick={() =>
                    setThresholdFilter(isSelected ? 'ALL' : String(rule.threshold_percent))
                  }
                  className="flex items-center gap-1.5 cursor-pointer"
                  title={`Filter alerts with threshold ${rule.threshold_percent}%`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      rule.enabled ? 'bg-emerald-400' : 'bg-muted-foreground/40'
                    }`}
                  />
                  <span className={`font-mono font-bold text-[11px] ${resColor}`}>{rule.resource}</span>
                  <span className="font-mono font-bold text-xs">{rule.threshold_percent}%</span>
                </button>

                {/* Subtle Hover Action Triggers */}
                <div className="flex items-center gap-0.5 ml-1 opacity-40 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={() => handleToggleRule(rule.id)}
                    className="p-0.5 text-muted-foreground hover:text-foreground cursor-pointer"
                    title={rule.enabled ? 'Click to disable' : 'Click to enable'}
                  >
                    <Power className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleOpenEditInline(rule)}
                    className="p-0.5 text-muted-foreground hover:text-foreground cursor-pointer"
                    title="Edit threshold"
                  >
                    <Edit2 className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      handleDeleteRule(rule.id, `${rule.resource} ${rule.threshold_percent}%`)
                    }
                    className="p-0.5 text-muted-foreground hover:text-rose-400 cursor-pointer"
                    title="Delete rule"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Sleek Inline Quick-Add / Quick-Edit Bar */}
        {isInlineOpen && (
          <form
            onSubmit={handleSaveRule}
            className="mt-3 flex flex-wrap items-center gap-3 rounded-[var(--radius-md)] border border-[var(--primary)]/40 bg-[var(--primary)]/5 p-3 text-xs animate-fade-in"
          >
            {/* Resource Selector */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase">Resource:</span>
              <select
                value={formResource}
                onChange={(e) => setFormResource(e.target.value as any)}
                className="rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1 text-xs font-mono font-semibold text-foreground focus:ring-1 focus:ring-[var(--primary)]"
              >
                <option value="CPU">CPU</option>
                <option value="RAM">RAM</option>
                <option value="Disk">Disk</option>
                <option value="ALL">ALL</option>
              </select>
            </div>

            {/* Threshold Percentage */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase">Threshold:</span>
              <div className="relative flex items-center">
                <input
                  type="number"
                  min="1"
                  max="100"
                  required
                  value={formThreshold}
                  onChange={(e) => setFormThreshold(Number(e.target.value))}
                  className="w-16 rounded-[var(--radius-sm)] border border-border bg-card px-2 py-1 pr-5 font-mono text-xs font-bold text-foreground focus:ring-1 focus:ring-[var(--primary)] text-center"
                />
                <span className="absolute right-1.5 text-[11px] font-mono text-muted-foreground select-none">%</span>
              </div>
            </div>

            {/* Quick Presets */}
            <div className="flex items-center gap-1">
              {[50, 70, 75, 80, 90, 95, 100].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setFormThreshold(preset)}
                  className={`rounded px-1.5 py-0.5 font-mono text-[10px] transition-colors cursor-pointer ${
                    formThreshold === preset
                      ? 'bg-[var(--primary)] text-white font-bold'
                      : 'bg-muted/40 text-muted-foreground hover:bg-muted'
                  }`}
                >
                  {preset}%
                </button>
              ))}
            </div>

            {/* Severity */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase">Severity:</span>
              <select
                value={formSeverity}
                onChange={(e) => setFormSeverity(e.target.value as any)}
                className="rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1 text-xs font-semibold text-foreground focus:ring-1 focus:ring-[var(--primary)]"
              >
                <option value="CRITICAL">CRITICAL</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>

            {/* Recipient Email (Optional) */}
            <div className="flex items-center gap-1.5 flex-1 min-w-[200px]">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase">Email:</span>
              <input
                type="email"
                placeholder="Optional recipient (default email if empty)"
                value={formRecipient}
                onChange={(e) => setFormRecipient(e.target.value)}
                className="flex-1 rounded-[var(--radius-sm)] border border-border bg-card px-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground/60 focus:ring-1 focus:ring-[var(--primary)]"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2 ml-auto">
              <button
                type="button"
                onClick={() => {
                  setIsInlineOpen(false);
                  setEditingRule(null);
                }}
                className="rounded-[var(--radius-sm)] border border-border bg-card px-3 py-1 text-xs text-muted-foreground hover:bg-muted cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSavingRule}
                className="flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--primary)] px-3 py-1 text-xs font-semibold text-white shadow-xs hover:bg-[var(--primary-hover)] disabled:opacity-50 cursor-pointer"
              >
                {isSavingRule && <RefreshCw className="h-3 w-3 animate-spin" />}
                <span>{editingRule ? 'Update' : 'Save Rule'}</span>
              </button>
            </div>
          </form>
        )}

        {/* Search Bar Integrated Inside Strip */}
        <div className="pt-2 border-t border-border/60 flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search alert notifications by subject, metric name, or recipient..."
              className="w-full rounded-[var(--radius-sm)] border border-border bg-muted/20 pl-9 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* ALERTS LOG STREAM (LATEST FIRST)                                          */}
      {/* ========================================================================= */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
          <div className="flex items-center gap-1.5">
            <Bell className="h-3.5 w-3.5 text-[var(--primary)]" />
            <span>
              Showing {filteredAlerts.length} of {sortedAlerts.length} Alerts
            </span>
          </div>
          <span className="font-mono text-[11px]">Sorted: Latest Alerts First</span>
        </div>

        {filteredAlerts.length > 0 ? (
          filteredAlerts.map((alert, idx) => (
            <div
              key={alert.id ?? idx}
              className="rounded-[var(--radius-lg)] border border-border bg-card p-4 shadow-[var(--shadow-resting)] transition-all hover:border-border/80"
            >
              <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                <div className="flex flex-wrap items-center gap-2">
                  {alert.threshold_level && (
                    <Badge
                      variant={
                        parseInt(alert.threshold_level.replace('%', ''), 10) >= 90
                          ? 'destructive'
                          : 'warning'
                      }
                      size="sm"
                    >
                      {alert.threshold_level}
                    </Badge>
                  )}
                  {alert.metric_name && (
                    <span className="font-mono text-xs font-semibold text-foreground">
                      {alert.metric_name}
                    </span>
                  )}
                  {alert.status && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      {alert.status}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span>
                    {alert.timestamp
                      ? new Date(alert.timestamp).toLocaleString(undefined, {
                          dateStyle: 'medium',
                          timeStyle: 'medium',
                        })
                      : 'Unknown time'}
                  </span>
                </div>
              </div>

              <h4 className="mt-2 text-sm font-semibold text-foreground">
                {alert.subject || 'Threshold alert'}
              </h4>

              {alert.details && (
                <p className="mt-1 text-xs text-muted-foreground font-mono bg-muted/20 p-2 rounded-[var(--radius-sm)] overflow-x-auto">
                  {typeof alert.details === 'string'
                    ? alert.details
                    : JSON.stringify(alert.details, null, 2)}
                </p>
              )}

              <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-2.5 text-xs text-muted-foreground font-mono">
                <span>
                  To: <strong className="text-foreground">{alert.recipient || 'Default Alert Email'}</strong>
                </span>
                <span>
                  Observed Usage: <strong className="text-foreground">{alert.value ?? 0}%</strong>
                </span>
              </div>
            </div>
          ))
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground rounded-[var(--radius-lg)] border border-border bg-card">
            <Mail className="h-8 w-8 text-muted-foreground/30 mb-2" />
            <p className="text-xs">
              No alerts found matching threshold &apos;{thresholdFilter}&apos; or search term.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
