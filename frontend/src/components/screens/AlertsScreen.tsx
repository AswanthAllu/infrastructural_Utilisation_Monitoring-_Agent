import React, { useState } from 'react';
import {
  Clock,
  Edit3,
  Mail,
  RefreshCw,
  Search,
} from 'lucide-react';
import { Badge } from '../common/Badge';
import { apiService } from '../../api/service';
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
  const [recipient, setRecipient] = useState('');
  const [editingRecipient, setEditingRecipient] = useState(false);
  const [recipientDraft, setRecipientDraft] = useState('');
  const [recipientError, setRecipientError] = useState('');

  const alerts = data?.alerts || [];

  React.useEffect(() => {
    apiService.getAlertRecipient().then((result) => setRecipient(result.email)).catch(() => undefined);
  }, []);

  const saveRecipient = async () => {
    const email = recipientDraft.trim();
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setRecipientError('Enter a valid email address.');
      return;
    }
    try {
      const result = await apiService.updateAlertRecipient(email);
      setRecipient(result.email);
      setEditingRecipient(false);
      setRecipientError('');
    } catch {
      setRecipientError('Unable to update the dispatch target.');
    }
  };

  const filteredAlerts = alerts.filter((alert) => {
    // Keep the screen resilient to older audit records that may not have all
    // normalized fields yet.
    const subject = alert.subject || 'Threshold alert';
    const metricName = alert.metric_name || 'Unknown metric';
    const recipient = alert.recipient || 'Unknown recipient';
    const thresholdLevel = alert.threshold_level || '';
    const matchesSearch =
      subject.toLowerCase().includes(searchTerm.toLowerCase()) ||
      metricName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      recipient.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesThreshold =
      thresholdFilter === 'ALL' || thresholdLevel.includes(thresholdFilter);

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

      {/* Active session dispatch target */}
      <div className="rounded-[var(--radius-lg)] border border-border bg-card p-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Primary Dispatch Target</span>
          <Mail className="h-4 w-4 text-[var(--primary)]" />
        </div>
        {editingRecipient ? (
          <div className="mt-2 flex flex-wrap gap-2">
            <input value={recipientDraft} onChange={(event) => setRecipientDraft(event.target.value)} autoFocus type="email" className="min-w-[260px] flex-1 rounded border border-border bg-background px-3 py-2 text-sm text-foreground" placeholder="Enter alert email" />
            <button onClick={saveRecipient} className="rounded bg-[var(--primary)] px-3 py-2 text-xs font-semibold text-white">Save</button>
            <button onClick={() => setEditingRecipient(false)} className="rounded border border-border px-3 py-2 text-xs">Cancel</button>
          </div>
        ) : (
          <div className="mt-2 flex items-center gap-2">
            <span className="truncate text-sm font-bold font-mono text-foreground">{recipient || 'Loading recipient...'}</span>
            <button onClick={() => { setRecipientDraft(recipient); setEditingRecipient(true); }} title="Edit dispatch target" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><Edit3 className="h-4 w-4" /></button>
          </div>
        )}
        {recipientError && <p className="mt-1 text-xs text-red-500">{recipientError}</p>}
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
                  {alert.threshold_level && (
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
                  )}
                  {alert.metric_name && (
                    <span className="font-mono text-xs font-semibold text-foreground">
                      {alert.metric_name}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span>{alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'Unknown time'}</span>
                </div>
              </div>

              <h4 className="mt-2 text-sm font-semibold text-foreground">
                {alert.subject || 'Threshold alert'}
              </h4>

              {alert.details && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {alert.details}
                </p>
              )}

              <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-2.5 text-xs text-muted-foreground font-mono">
                <span>To: <strong className="text-foreground">{alert.recipient || 'Unknown recipient'}</strong></span>
                <span>Observed: <strong className="text-foreground">{alert.value ?? 0}%</strong></span>
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
