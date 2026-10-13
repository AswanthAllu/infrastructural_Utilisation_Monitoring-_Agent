import React, { useState } from 'react';
import {
  Database,
  RefreshCw,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import type { IncidentRecord, IncidentReviewResponse } from '../../types';

interface BigQueryScreenProps {
  data: IncidentReviewResponse | null;
  isLoading: boolean;
  onRefresh: (region?: string, lookback?: number, limit?: number) => void;
}

export const BigQueryScreen: React.FC<BigQueryScreenProps> = ({
  data,
  isLoading,
  onRefresh,
}) => {
  const [selectedRegion, setSelectedRegion] = useState('US');
  const [lookbackHours, setLookbackHours] = useState(24);
  const [jobsLimit, setJobsLimit] = useState(5);
  const [selectedIncident, setSelectedIncident] = useState<IncidentRecord | null>(null);

  const incidents = data?.incidents || [];

  const handleApplyFilters = () => {
    onRefresh(selectedRegion, lookbackHours, jobsLimit);
  };

  const getFailureModeBadge = (mode?: string) => {
    if (!mode) return null;
    switch (mode) {
      case 'KEY_SKEW':
        return <Badge variant="destructive" size="sm">KEY_SKEW (Hot Key)</Badge>;
      case 'FAN_OUT':
        return <Badge variant="warning" size="sm">FAN_OUT (Multiplication)</Badge>;
      case 'SHUFFLE_VOLUME':
        return <Badge variant="info" size="sm">SHUFFLE_VOLUME (Heavy)</Badge>;
      case 'UNCONSTRAINED_JOIN':
        return <Badge variant="destructive" size="sm">UNCONSTRAINED_JOIN (Cartesian)</Badge>;
      default:
        return <Badge variant="neutral" size="sm">{mode}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Badge variant="destructive" size="sm">
              BIGQUERY INCIDENT AUDITOR
            </Badge>
            <span className="text-xs font-mono text-muted-foreground">/api/review</span>
          </div>
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            BigQuery Reliability & Cost-Risk Support System
          </h2>
          <p className="text-xs text-muted-foreground">
            Reviews <code className="font-mono text-foreground">INFORMATION_SCHEMA.JOBS</code>, classifies join failure modes, detects missing partition filters, and audits slot throttling.
          </p>
        </div>

        <button
          onClick={handleApplyFilters}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[var(--primary-hover)] disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Scanning Jobs...' : 'Run Incident Review'}</span>
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-medium text-muted-foreground">Region:</span>
            <select
              value={selectedRegion}
              onChange={(e) => setSelectedRegion(e.target.value)}
              className="rounded-[var(--radius-sm)] border border-border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value="US">US (Multi-region)</option>
              <option value="EU">EU (Multi-region)</option>
              <option value="us-central1">us-central1 (Iowa)</option>
              <option value="us-east1">us-east1 (South Carolina)</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-medium text-muted-foreground">Lookback:</span>
            <select
              value={lookbackHours}
              onChange={(e) => setLookbackHours(Number(e.target.value))}
              className="rounded-[var(--radius-sm)] border border-border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value={1}>Last 1 Hour</option>
              <option value={6}>Last 6 Hours</option>
              <option value={24}>Last 24 Hours</option>
              <option value={48}>Last 48 Hours</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-medium text-muted-foreground">Jobs Limit:</span>
            <select
              value={jobsLimit}
              onChange={(e) => setJobsLimit(Number(e.target.value))}
              className="rounded-[var(--radius-sm)] border border-border bg-background px-2.5 py-1 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value={5}>5 Jobs</option>
              <option value={10}>10 Jobs</option>
              <option value={25}>25 Jobs</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <span>Analyzed: <strong className="text-foreground">{data?.jobs_analyzed || 5}</strong></span>
          <span>•</span>
          <span>Incidents: <strong className="text-[var(--destructive)]">{incidents.length}</strong></span>
        </div>
      </div>

      {/* Incidents Table / Cards */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Incident List */}
        <div className="space-y-3 lg:col-span-2">
          {incidents.map((inc) => {
            const isSelected = selectedIncident?.incident_id === inc.incident_id;
            return (
              <div
                key={inc.incident_id}
                onClick={() => setSelectedIncident(inc)}
                className={`cursor-pointer rounded-[var(--radius-lg)] border p-4 transition-all ${
                  isSelected
                    ? 'border-[var(--primary)] bg-[var(--primary-tint)]/40 ring-1 ring-[var(--primary)]'
                    : 'border-border bg-card hover:border-border/80 hover:bg-muted/30'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-foreground">
                        {inc.incident_id}
                      </span>
                      <Badge
                        variant={inc.severity === 'CRITICAL' ? 'destructive' : inc.severity === 'HIGH' ? 'warning' : 'info'}
                        size="sm"
                      >
                        {inc.severity}
                      </Badge>
                      <Badge variant="primary" size="sm">
                        {inc.incident_type}
                      </Badge>
                      {inc.failure_mode && getFailureModeBadge(inc.failure_mode)}
                    </div>
                    <h4 className="mt-2 text-sm font-semibold text-foreground">
                      {inc.summary || inc.incident_type}
                    </h4>
                  </div>

                  <span className="font-mono text-[11px] text-muted-foreground whitespace-nowrap">
                    {inc.status}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground font-mono">
                  {inc.job_id && (
                    <span>Job: <span className="text-foreground">{inc.job_id}</span></span>
                  )}
                  {inc.table_name && (
                    <span>Table: <span className="text-foreground">{inc.table_name}</span></span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Selected Incident Inspector */}
        <div className="space-y-4">
          <Card
            title={selectedIncident ? selectedIncident.incident_id : 'Incident Inspector'}
            subtitle={selectedIncident ? selectedIncident.incident_type : 'Select an incident from the left to inspect details'}
          >
            {selectedIncident ? (
              <div className="space-y-4 text-xs">
                <div>
                  <span className="font-semibold text-muted-foreground">Impact & Classification:</span>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {selectedIncident.summary}
                  </p>
                </div>

                {selectedIncident.failure_mode && (
                  <div className="rounded-[var(--radius-sm)] border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-3 text-[var(--status-error-text)]">
                    <span className="font-bold">Join Pathology: {selectedIncident.failure_mode}</span>
                    <p className="mt-1 text-[11px] text-[var(--status-error-text)]/90">
                      Classified via SQL ast (sqlglot) and execution plan stages.
                    </p>
                  </div>
                )}

                {selectedIncident.query && (
                  <div>
                    <span className="font-semibold text-muted-foreground">Offending SQL Statement:</span>
                    <pre className="mt-1 max-h-36 overflow-auto rounded-[var(--radius-sm)] border border-border bg-[#0B1220] p-2.5 font-mono text-[11px] text-[#E7EBF3]">
                      <code>{selectedIncident.query}</code>
                    </pre>
                  </div>
                )}

                <div>
                  <span className="font-semibold text-muted-foreground">Diagnostic Evidence:</span>
                  <div className="mt-1 rounded-[var(--radius-sm)] bg-muted/40 p-2.5 font-mono text-[11px] space-y-1">
                    {Object.entries(selectedIncident.evidence || {}).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-muted-foreground">{k}:</span>
                        <span className="text-foreground font-semibold">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {selectedIncident.metadata && (
                  <div>
                    <span className="font-semibold text-muted-foreground">Operational Cost Impact:</span>
                    <div className="mt-1 rounded-[var(--radius-sm)] border border-border/80 bg-muted/20 p-2 text-foreground">
                      {Object.entries(selectedIncident.metadata).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-[11px]">
                          <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}:</span>
                          <span className="font-medium text-foreground">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <Database className="h-8 w-8 text-muted-foreground/40 mb-2" />
                <p className="text-xs">Click on any incident card to view query text, execution plan stages, and evidence.</p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
