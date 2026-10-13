import React, { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Mail,
  RefreshCw,
  Search,
  ShieldAlert,
} from 'lucide-react';
import { Badge } from '../common/Badge';
import type { EmailAlertsResponse } from '../../types';

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

  const alerts = data?.alerts || [];

  const filteredAlerts = alerts.filter((alert) => {
    const matchesSearch =
      alert.subject.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alert.metric_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      alert.recipient.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesThreshold =
      thresholdFilter === 'ALL' || alert.threshold_level.includes(thresholdFilter);

    return matchesSearch && matchesThreshold;
  });

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm">
              NODEMAILER AUDIT TRAIL
            </Badge>
            <span className="text-xs font-mono text-muted-foreground">/api/metrics/alerts</span>
          </div>
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            Threshold Alert Dispatch & Notification Log
          </h2>
          <p className="text-xs text-muted-foreground">
            Audits all high-priority alerts sent when CPU, Memory, or Disk metrics breach the 50%, 70%, or 100% threshold levels.
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[var(--primary-hover)] disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Reloading...' : 'Refresh Alerts'}</span>
        </button>
      </div>

      {/* Summary Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Total Threshold Triggers</span>
            <ShieldAlert className="h-4 w-4 text-[var(--warning)]" />
          </div>
          <div className="mt-2 text-2xl font-bold font-heading text-foreground">
            {data?.total_alerts || alerts.length} Dispatched
          </div>
          <p className="mt-1 text-xs text-muted-foreground">From automated background poller</p>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Primary Dispatch Target</span>
            <Mail className="h-4 w-4 text-[var(--primary)]" />
          </div>
          <div className="mt-2 text-sm font-bold font-mono text-foreground truncate">
            {import.meta.env.VITE_DEFAULT_ALERT_EMAIL}
          </div>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-border bg-card p-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Single Consolidated Policy</span>
            <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
          </div>
          <div className="mt-2 text-2xl font-bold font-heading text-[var(--success)]">
            Active
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Sends highest threshold only</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-border bg-card p-4">
        <div className="relative min-w-[240px] flex-1">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by subject, metric name, or recipient..."
            className="w-full rounded-[var(--radius-sm)] border border-border bg-background py-1.5 pl-9 pr-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
          />
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Threshold:</span>
          {['ALL', '50', '70', '100'].map((lvl) => (
            <button
              key={lvl}
              onClick={() => setThresholdFilter(lvl)}
              className={`rounded-[var(--radius-sm)] px-2.5 py-1 font-mono text-xs transition-colors ${
                thresholdFilter === lvl
                  ? 'bg-[var(--primary)] text-white'
                  : 'bg-muted/40 text-muted-foreground hover:bg-muted'
              }`}
            >
              {lvl === 'ALL' ? 'All' : `${lvl}%`}
            </button>
          ))}
        </div>
      </div>

      {/* Alerts Log Stream */}
      <div className="space-y-3">
        {filteredAlerts.length > 0 ? (
          filteredAlerts.map((alert, idx) => (
            <div
              key={idx}
              className="rounded-[var(--radius-lg)] border border-border bg-card p-4 shadow-[var(--shadow-resting)] transition-all hover:border-border/80"
            >
              <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={
                      alert.threshold_level.includes('70') || alert.threshold_level.includes('100')
                        ? 'destructive'
                        : 'warning'
                    }
                    size="sm"
                  >
                    {alert.threshold_level}
                  </Badge>
                  <span className="font-mono text-xs font-semibold text-foreground">
                    {alert.metric_name}
                  </span>
                  <Badge variant="success" size="sm">
                    {alert.status}
                  </Badge>
                </div>

                <div className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span>{new Date(alert.timestamp).toLocaleString()}</span>
                </div>
              </div>

              <h4 className="mt-2 text-sm font-semibold text-foreground">
                {alert.subject}
              </h4>

              {alert.details && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {alert.details}
                </p>
              )}

              <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-2.5 text-xs text-muted-foreground font-mono">
                <span>To: <strong className="text-foreground">{alert.recipient}</strong></span>
                <span>Observed: <strong className="text-foreground">{alert.value}%</strong></span>
              </div>
            </div>
          ))
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground rounded-[var(--radius-lg)] border border-border bg-card">
            <Mail className="h-8 w-8 text-muted-foreground/30 mb-2" />
            <p className="text-xs">No alerts found matching your search filter.</p>
          </div>
        )}
      </div>
    </div>
  );
};
