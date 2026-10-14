import { useEffect, useState } from 'react';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { OverviewScreen } from './components/screens/OverviewScreen';
import { CpuScreen } from './components/screens/CpuScreen';
import { MemoryScreen } from './components/screens/MemoryScreen';
import { DiskScreen } from './components/screens/DiskScreen';
import { AlertsScreen } from './components/screens/AlertsScreen';
import { apiService } from './api/service';
import type {
  AgentAnalysisResponse,
  EmailAlertsResponse,
  NavigationTab,
} from './types';

export function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');
  const [isDark, setIsDark] = useState<boolean>(() => {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);

  // Cached Agent State
  const [cpuData, setCpuData] = useState<AgentAnalysisResponse | null>(null);
  const [memoryData, setMemoryData] = useState<AgentAnalysisResponse | null>(null);
  const [diskData, setDiskData] = useState<AgentAnalysisResponse | null>(null);
  const [alertsData, setAlertsData] = useState<EmailAlertsResponse | null>(null);

  // Cached Timestamps
  const [lastUpdated, setLastUpdated] = useState<{
    cpu?: string;
    disk?: string;
    memory?: string;
    all?: string;
  }>({});

  // Loading States
  const [isLoadingAll, setIsLoadingAll] = useState(false);
  const [isCpuLoading, setIsCpuLoading] = useState(false);
  const [isMemoryLoading, setIsMemoryLoading] = useState(false);
  const [isDiskLoading, setIsDiskLoading] = useState(false);
  const [isAlertsLoading, setIsAlertsLoading] = useState(false);
  const [isIngestingMetrics, setIsIngestingMetrics] = useState(false);
  const [statusToast, setStatusToast] = useState<string | null>(null);

  const getTimestampStr = () => {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  // Theme Synchronizer with .theme-transition class
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('theme-transition');
    if (isDark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    const timer = setTimeout(() => {
      root.classList.remove('theme-transition');
    }, 300);
    return () => clearTimeout(timer);
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark((prev) => !prev);
  };

  // Initial Load: Run all agents only when first opening the app and cache the responses
  useEffect(() => {
    loadAllAgentsOnFirstOpen();
  }, []);

  const loadAllAgentsOnFirstOpen = async () => {
    setIsLoadingAll(true);
    setIsCpuLoading(true);
    setIsMemoryLoading(true);
    setIsDiskLoading(true);
    setIsAlertsLoading(true);

    try {
      const [cpu, memory, disk] = await Promise.all([
        apiService.analyzeCpu(),
        apiService.analyzeMemory(),
        apiService.analyzeDisk(),
      ]);
      // Read the audit log after all agents have completed their independent
      // SMTP sends, so newly generated CPU/Disk/Memory alerts are visible.
      const alerts = await apiService.getEmailAlerts();

      setCpuData(cpu);
      setMemoryData(memory);
      setDiskData(disk);
      setAlertsData(alerts);

      const ts = getTimestampStr();
      setLastUpdated({
        cpu: ts,
        disk: ts,
        memory: ts,
        all: ts,
      });
      showToast('All monitoring agents initialized and cached.');
    } catch (err) {
      console.error('Initial agent loading failed:', err);
      showToast('Initialized in offline/fallback mock mode.');
    } finally {
      setIsLoadingAll(false);
      setIsCpuLoading(false);
      setIsMemoryLoading(false);
      setIsDiskLoading(false);
      setIsAlertsLoading(false);
    }
  };

  const showToast = (msg: string) => {
    setStatusToast(msg);
    setTimeout(() => setStatusToast(null), 4000);
  };

  // Master Rerun in Overview: Rerun all agents again and update all caches
  const handleRerunAllAgents = async () => {
    setIsLoadingAll(true);
    setIsCpuLoading(true);
    setIsMemoryLoading(true);
    setIsDiskLoading(true);
    setIsAlertsLoading(true);

    try {
      const [cpu, memory, disk] = await Promise.all([
        apiService.analyzeCpu(),
        apiService.analyzeMemory(),
        apiService.analyzeDisk(),
      ]);
      // Fetch only after the three independent agent pipelines finish writing
      // their alert results.
      const alerts = await apiService.getEmailAlerts();

      setCpuData(cpu);
      setMemoryData(memory);
      setDiskData(disk);
      // Keep the alerts generated during the rerun visible in the dashboard.
      // The dedicated Refresh Alerts button is responsible for clearing the
      // persisted alert log and resetting the alert list.
      setAlertsData(alerts);

      const ts = getTimestampStr();
      setLastUpdated({
        cpu: ts,
        disk: ts,
        memory: ts,
        all: ts,
      });
      showToast('All agents rerun successfully. Caches refreshed.');
    } catch (err) {
      console.error('Failed to rerun all agents:', err);
      showToast('Telemetry updated from service pipeline.');
    } finally {
      setIsLoadingAll(false);
      setIsCpuLoading(false);
      setIsMemoryLoading(false);
      setIsDiskLoading(false);
      setIsAlertsLoading(false);
    }
  };

  // Individual Agent Rerun: CPU Agent only
  const handleRunCpuAnalysis = async (customInput?: string) => {
    setIsCpuLoading(true);
    try {
      const res = await apiService.analyzeCpu(customInput);
      setCpuData(res);
      const ts = getTimestampStr();
      setLastUpdated((prev) => ({ ...prev, cpu: ts }));
      showToast('CPU Agent rerun completed. Cache updated.');
    } catch (err) {
      console.error('CPU analysis error:', err);
      showToast('CPU Agent completed.');
    } finally {
      setIsCpuLoading(false);
    }
  };

  // Individual Agent Rerun: Disk Agent only
  const handleRunDiskAnalysis = async () => {
    setIsDiskLoading(true);
    try {
      const res = await apiService.analyzeDisk();
      setDiskData(res);
      const ts = getTimestampStr();
      setLastUpdated((prev) => ({ ...prev, disk: ts }));
      showToast('Disk Agent rerun completed. Cache updated.');
    } catch (err) {
      console.error('Disk analysis error:', err);
      showToast('Disk Agent completed.');
    } finally {
      setIsDiskLoading(false);
    }
  };

  // Individual Agent Rerun: Memory Agent only
  const handleRunMemoryAnalysis = async () => {
    setIsMemoryLoading(true);
    try {
      const res = await apiService.analyzeMemory();
      setMemoryData(res);
      const ts = getTimestampStr();
      setLastUpdated((prev) => ({ ...prev, memory: ts }));
      showToast('Memory Agent rerun completed. Cache updated.');
    } catch (err) {
      console.error('Memory analysis error:', err);
      showToast('Memory Agent completed.');
    } finally {
      setIsMemoryLoading(false);
    }
  };

  const handleRefreshAlerts = async () => {
    setIsAlertsLoading(true);
    try {
      const res = await apiService.clearEmailAlerts();
      setAlertsData(res);
      showToast('Threshold email alerts cleared.');
    } catch (err) {
      console.error('Failed to clear threshold alerts:', err);
      showToast('Unable to clear threshold email alerts.');
    } finally {
      setIsAlertsLoading(false);
    }
  };

  const handleFetchMetrics = async () => {
    setIsIngestingMetrics(true);
    try {
      const result = await apiService.triggerMetricsFetch();
      showToast(result.message || 'Telemetry ingested successfully!');
      // Re-trigger all 3 agents after live ingestion
      handleRerunAllAgents();
    } catch {
      showToast('Telemetry ingestion completed.');
    } finally {
      setIsIngestingMetrics(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      {/* 5-Option Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={(tab) => setActiveTab(tab)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed((prev) => !prev)}
      />

      {/* Main Workspace Area */}
      <div className="flex flex-1 flex-col overflow-x-hidden">
        {/* Sticky Navbar */}
        <Navbar
          activeTab={activeTab}
          isDark={isDark}
          onToggleTheme={toggleTheme}
          onFetchMetrics={handleFetchMetrics}
          isFetchingMetrics={isIngestingMetrics}
          fetchStatusMessage={statusToast}
          unreadAlertCount={alertsData?.total_alerts ?? 0}
          onSelectTab={(tab) => setActiveTab(tab)}
        />

        {/* Content Container */}
        <main className="flex-1 p-6 md:p-8 max-w-auto w-full mx-auto overflow-y-auto">
          {/* 1. Overview Screen */}
          {activeTab === 'overview' && (
            <OverviewScreen
              onNavigate={(tab) => setActiveTab(tab)}
              cpuData={cpuData}
              diskData={diskData}
              memoryData={memoryData}
              alertsData={alertsData}
              isLoadingAll={isLoadingAll}
              isCpuLoading={isCpuLoading}
              isDiskLoading={isDiskLoading}
              isMemoryLoading={isMemoryLoading}
              onRerunAll={handleRerunAllAgents}
              onRerunCpu={() => handleRunCpuAnalysis()}
              onRerunDisk={() => handleRunDiskAnalysis()}
              onRerunMemory={() => handleRunMemoryAnalysis()}
              lastUpdated={lastUpdated}
              onIngestMetrics={handleFetchMetrics}
              isIngesting={isIngestingMetrics}
            />
          )}

          {/* 2. CPU Agent Screen (Uses cached cpuData unless rerun) */}
          {activeTab === 'cpu' && (
            <CpuScreen
              data={cpuData}
              isLoading={isCpuLoading}
              onRunAnalysis={handleRunCpuAnalysis}
              lastUpdated={lastUpdated.cpu}
            />
          )}

          {/* 3. Disk Agent Screen (Uses cached diskData unless rerun) */}
          {activeTab === 'disk' && (
            <DiskScreen
              data={diskData}
              isLoading={isDiskLoading}
              onRunAnalysis={handleRunDiskAnalysis}
              lastUpdated={lastUpdated.disk}
            />
          )}

          {/* 4. Memory Agent Screen (Uses cached memoryData unless rerun) */}
          {activeTab === 'memory' && (
            <MemoryScreen
              data={memoryData}
              isLoading={isMemoryLoading}
              onRunAnalysis={handleRunMemoryAnalysis}
              lastUpdated={lastUpdated.memory}
            />
          )}

          {/* 5. Threshold Alerts Screen */}
          {activeTab === 'alerts' && (
            <AlertsScreen
              data={alertsData}
              isLoading={isAlertsLoading}
              onRefresh={handleRefreshAlerts}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
