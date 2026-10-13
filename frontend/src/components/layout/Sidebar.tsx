import React from 'react';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Cpu,
  HardDrive,
  Layers,
  LayoutDashboard,
} from 'lucide-react';
import type { NavigationTab } from '../../types';

interface SidebarProps {
  activeTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  alertCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  isCollapsed,
  onToggleCollapse,
  alertCount,
}) => {
  const navItems = [
    {
      id: 'overview' as NavigationTab,
      label: 'Overview',
      icon: LayoutDashboard,
      badge: null,
      desc: 'System health & all agents',
    },
    {
      id: 'cpu' as NavigationTab,
      label: 'CPU Agent',
      icon: Cpu,
      badge: '',
      desc: 'Slots, spikes & contention',
    },
    {
      id: 'disk' as NavigationTab,
      label: 'Disk Agent',
      icon: HardDrive,
      badge: 'I/O',
      desc: 'Storage & log rotators',
    },
    {
      id: 'memory' as NavigationTab,
      label: 'Memory Agent',
      icon: Layers,
      badge: 'RAM',
      desc: 'Heap & leak mitigation',
    },
    {
      id: 'alerts' as NavigationTab,
      label: 'Threshold Alerts',
      icon: AlertTriangle,
      badge: alertCount > 0 ? String(alertCount) : null,
      desc: '50% / 70% / 100% email logs',
    },
  ];

  return (
    <aside
      className={`relative flex flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] text-[var(--sidebar-foreground)] transition-all duration-300 ease-in-out ${
        isCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Header & Logo Lockup */}
      <div className="flex h-16 items-center justify-between border-b border-[var(--sidebar-border)] px-4">
        <div className="flex items-center gap-3 overflow-hidden">
          {/* Custom SVG Logo */}
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
            <img src="/labs_for_dark.png" alt="Logo" />
          </div>

          {!isCollapsed && (
            <div className="flex flex-col overflow-hidden">
              <span className="font-heading text-sm font-extrabold tracking-tight text-white">
                Infrastructure Utilization Monitoring
              </span>
            </div>
          )}
        </div>

        {/* Sidebar Collapse Toggle Button */}
        <button
          onClick={onToggleCollapse}
          className="rounded-[var(--radius-sm)] p-1 text-[var(--sidebar-muted-foreground)] transition-colors hover:bg-[var(--sidebar-accent)] hover:text-white"
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation Links */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1.5 scrollbar-thin">
        <div className={`px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-[var(--sidebar-muted-foreground)] ${isCollapsed ? 'text-center' : ''}`}>
          {isCollapsed ? '•••' : 'Agents & Auditing'}
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              title={isCollapsed ? `${item.label} — ${item.desc}` : undefined}
              className={`group flex w-full items-center gap-3 rounded-[var(--radius-md)] px-3 py-2.5 text-xs font-medium transition-all ${
                isActive
                  ? 'bg-[var(--sidebar-primary)] text-[var(--sidebar-primary-foreground)] shadow-[inset_0_0_0_1px_rgba(0,170,231,0.25)] font-semibold'
                  : 'text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)]'
              }`}
            >
              <Icon
                className={`h-4 w-4 shrink-0 transition-transform group-hover:scale-110 ${
                  isActive ? 'text-[var(--primary)]' : 'text-[var(--sidebar-muted-foreground)]'
                }`}
              />

              {!isCollapsed && (
                <div className="flex flex-1 items-center justify-between text-left">
                  <div>
                    <div className="leading-tight">{item.label}</div>
                    <div className="text-[10px] text-[var(--sidebar-muted-foreground)] font-normal">
                      {item.desc}
                    </div>
                  </div>

                  {item.badge && (
                    <span
                      className={`ml-2 rounded-[var(--radius-sm)] px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                        item.id === 'alerts' && alertCount > 0
                          ? 'bg-[var(--destructive)] text-white animate-pulse'
                          : isActive
                          ? 'bg-[var(--primary)]/20 text-[var(--primary)]'
                          : 'bg-white/10 text-[var(--sidebar-muted-foreground)]'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </aside>
  );
};
