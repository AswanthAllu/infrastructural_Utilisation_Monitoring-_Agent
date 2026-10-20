import React from 'react';
import {
  Bell,
  CheckCircle2,
  Moon,
  Sun,
} from 'lucide-react';
import type { NavigationTab } from '../../types';

interface NavbarProps {
  activeTab: NavigationTab;
  isDark: boolean;
  onToggleTheme: () => void;
  onFetchMetrics?: () => void;
  isFetchingMetrics?: boolean;
  fetchStatusMessage?: string | null;
  unreadAlertCount: number;
  onSelectTab: (tab: NavigationTab) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  isDark,
  onToggleTheme,
  onFetchMetrics: _onFetchMetrics,
  isFetchingMetrics: _isFetchingMetrics,
  fetchStatusMessage,
  unreadAlertCount,
  onSelectTab,
}) => {
  const getTabLabel = (tab: NavigationTab) => {
    switch (tab) {
      case 'overview':
        return 'Overview & System Health';
      case 'cpu':
        return 'CPU Agent & Slot Telemetry';
      case 'memory':
        return 'Memory & RAM Optimization Agent';
      case 'disk':
        return 'Disk Storage & I/O Agent';
      case 'bigquery':
        return 'BigQuery Incident Review';
      case 'orchestrator':
        return 'Master Orchestrator Agent';
      case 'alerts':
        return 'Threshold Email Alerts';
      case 'history':
        return 'Remediation Decision History & Audit Log';
      default:
        return 'Reliability Dashboard';
    }
  };

  return (
    <header className="sticky top-0 z-40 flex h-16 w-full items-center justify-between border-b border-border bg-card/95 px-6 backdrop-blur-md transition-colors shadow-sm">
      {/* Left Breadcrumb & Page title */}
      <div className="flex items-center gap-3">
        {/* <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <span className="font-mono">AGENTS</span>
          <span>/</span>
          <span className="text-[var(--primary)] font-semibold uppercase">{activeTab}</span>
        </div> 
        <div className="hidden h-4 w-px bg-border sm:block" />*/}
        <h1 className="font-heading text-lg font-bold text-foreground">
          {getTabLabel(activeTab)}
        </h1>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3">
        {/* Backend Connectivity Status
        <div className="hidden items-center gap-2 rounded-full border border-border bg-muted/30 px-3 py-1 text-xs md:flex">
          <Server className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-mono text-muted-foreground">API:</span>
          <span className="font-mono font-medium text-foreground">localhost:8000</span>
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--success)] opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--success)]"></span>
          </span>
        </div> */}

        {/* Fetch Live Telemetry Button */}
        {/* <button
          onClick={onFetchMetrics}
          disabled={isFetchingMetrics}
          data-slot="button"
          title="Trigger ingestion from http://20.15.164.79:8080/api/history"
          className="flex items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--primary)]/40 bg-[var(--primary-tint)] px-3 py-1.5 text-xs font-medium text-[var(--primary)] transition-all hover:bg-[var(--primary)] hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetchingMetrics ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">
            {isFetchingMetrics ? 'Ingesting...' : 'Ingest Telemetry'}
          </span>
        </button> */}

        {/* Quick status toast */}
        {fetchStatusMessage && (
          <div className="hidden items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--status-success-bg)] px-2.5 py-1 text-xs text-[var(--status-success-text)] border border-[var(--status-success-border)] lg:flex animate-fade-in">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span className="truncate max-w-[200px]">{fetchStatusMessage}</span>
          </div>
        )}

        {/* Alert Notifications Button */}
        <button
          onClick={() => onSelectTab('alerts')}
          className="relative rounded-[var(--radius-md)] p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          title="Threshold email notifications"
          aria-label="View notifications"
        >
          <Bell className="h-4 w-4" />
          {unreadAlertCount > 0 && (
            <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--destructive)] text-[10px] font-bold text-white shadow-sm animate-pulse">
              {unreadAlertCount}
            </span>
          )}
        </button>

        {/* Theme Toggle (Dark / Light) */}
        <button
          onClick={onToggleTheme}
          className="rounded-[var(--radius-md)] p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
          aria-label="Toggle theme"
        >
          {isDark ? (
            <Sun className="h-4 w-4 text-amber-400" />
          ) : (
            <Moon className="h-4 w-4 text-slate-700" />
          )}
        </button>

        {/* User Lockup */}
        <div className="hidden items-center gap-2.5 border-l border-border pl-3 md:flex">
          <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-tr from-[var(--primary)] to-[var(--primary-hover)] text-xs font-bold text-white shadow-sm">
            SN
            <span className="absolute bottom-0 right-0 h-2 w-2 rounded-full bg-[var(--success)] ring-2 ring-card" />
          </div>
          <div className="flex flex-col text-left">
            {/* <span className="text-xs font-semibold leading-tight text-foreground">SV</span> */}
            {/* <span className="text-[11px] leading-tight text-muted-foreground">vnarava@miraclesoft.com</span> */}
          </div>
        </div>
      </div>
    </header>
  );
};
