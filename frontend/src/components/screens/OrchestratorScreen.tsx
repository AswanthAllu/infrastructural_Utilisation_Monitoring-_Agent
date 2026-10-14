import React, { useState } from 'react';
import {
  FileUp,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { RemediationList } from '../common/RemediationList';
import type { OrchestratorAnalysisResponse } from '../../types';

interface OrchestratorScreenProps {
  onAnalyze: (input: { text?: string; file?: File; filename?: string }) => Promise<OrchestratorAnalysisResponse>;
  isLoading: boolean;
}

export const OrchestratorScreen: React.FC<OrchestratorScreenProps> = ({
  onAnalyze,
  isLoading,
}) => {
  const [inputText, setInputText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<OrchestratorAnalysisResponse | null>(null);

  const sampleCpuLog = `timestamp,metric_type,project_id,job_id,avg_slots_utilized,total_slot_ms,runtime_seconds,query
2026-10-12 15:30:00,BQ_CPU_USAGE,corp-analytics-prod,bqjob_098231a,22.4,9823102,185.0,"SELECT * FROM prod.events WHERE customer_id = 'c129'"`;

  const sampleDiskLog = `timestamp,used_gb,free_gb,total_gb,percent,mount
2026-10-12 15:30:00,165.2,34.8,200.0,82.6,/dev/sda1`;

  const handleSubmit = async () => {
    if (!inputText && !selectedFile) return;
    const res = await onAnalyze({
      text: inputText,
      file: selectedFile || undefined,
      filename: selectedFile?.name,
    });
    setResult(res);
  };

  return (
    <div className="space-y-6">
      {/* Screen Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Badge variant="primary" size="sm">
              MASTER ORCHESTRATOR
            </Badge>
            <span className="text-xs font-mono text-muted-foreground">/api/orchestrator/analyze</span>
          </div>
          <h2 className="mt-1 font-heading text-xl font-bold text-foreground">
            Multi-Agent Workload Orchestrator & Dispatcher
          </h2>
          <p className="text-xs text-muted-foreground">
            Ingests workload telemetry or log files, classifies compute and storage characteristics, and delegates to specialized subagents with FinOps guardrails.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Input Panel */}
        <div className="space-y-4">
          <Card
            title="Workload Telemetry Input"
            subtitle="Upload a .csv file or paste raw telemetry text"
          >
            <div className="space-y-4">
              {/* File Upload Drop Area */}
              <div className="relative rounded-[var(--radius-md)] border-2 border-dashed border-border p-4 text-center hover:border-[var(--primary)] transition-colors">
                <input
                  type="file"
                  accept=".csv,.txt,.log,.json"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      setSelectedFile(e.target.files[0]);
                    }
                  }}
                  className="absolute inset-0 cursor-pointer opacity-0"
                />
                <div className="flex flex-col items-center justify-center gap-1.5 text-xs text-muted-foreground">
                  <FileUp className="h-6 w-6 text-[var(--primary)]" />
                  <span className="font-medium text-foreground">
                    {selectedFile ? selectedFile.name : 'Click or drop .csv / log file here'}
                  </span>
                  <span>Supports BigQuery CPU logs, telemetry history JSON, or raw logs</span>
                </div>
              </div>

              {selectedFile && (
                <div className="flex items-center justify-between rounded-[var(--radius-sm)] bg-muted/40 px-3 py-1.5 text-xs">
                  <span className="font-mono text-foreground">{selectedFile.name}</span>
                  <button
                    onClick={() => setSelectedFile(null)}
                    className="text-[var(--destructive)] hover:underline text-xs"
                  >
                    Remove
                  </button>
                </div>
              )}

              {/* Text Input */}
              <div>
                <div className="flex items-center justify-between pb-1.5 text-xs text-muted-foreground">
                  <span>Or enter telemetry text directly:</span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setInputText(sampleCpuLog)}
                      className="text-[var(--primary)] hover:underline text-[11px]"
                    >
                      Fill CPU Sample
                    </button>
                    <span>•</span>
                    <button
                      onClick={() => setInputText(sampleDiskLog)}
                      className="text-[var(--primary)] hover:underline text-[11px]"
                    >
                      Fill Disk Sample
                    </button>
                  </div>
                </div>
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="Paste CSV rows, JSON telemetry, or error messages here..."
                  rows={6}
                  className="w-full rounded-[var(--radius-md)] border border-border bg-background p-3 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
                />
              </div>

              <button
                onClick={handleSubmit}
                disabled={isLoading || (!inputText.trim() && !selectedFile)}
                className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-md)] bg-[var(--primary)] py-2 text-xs font-semibold text-white shadow-sm transition-all hover:bg-[var(--primary-hover)] disabled:opacity-50"
              >
                {isLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                <span>{isLoading ? 'Orchestrating Workflow...' : 'Orchestrate & Dispatch Workload'}</span>
              </button>
            </div>
          </Card>
        </div>

        {/* Results Panel */}
        <div className="space-y-4">
          <Card
            title="Orchestration Routing & Output"
            subtitle={result ? `Workflow ID: ${result.workflow_id || 'ACTIVE'}` : 'Awaiting input'}
            action={
              result && (
                <Badge variant="primary" size="sm">
                  {result.designated_agent?.toUpperCase()}
                </Badge>
              )
            }
          >
            {result ? (
              <div className="space-y-4 text-xs">
                {/* Routing Banner */}
                <div className="rounded-[var(--radius-md)] border border-[var(--primary)]/30 bg-[var(--primary-tint)] p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-[var(--primary)]">Target Subagent:</span>
                    <Badge variant="primary" size="sm">{result.designated_agent}</Badge>
                  </div>
                  <div className="mt-2 text-xs text-foreground">
                    <div>Routed By: <strong className="font-mono">{result.routed_by}</strong></div>
                    <div>Workload Class: <strong className="font-mono">{result.workload_classification}</strong></div>
                  </div>
                </div>

                {/* Subagent Detection */}
                <div>
                  <span className="font-semibold text-muted-foreground">Subagent Detection Summary:</span>
                  <p className="mt-1 text-sm font-medium text-foreground">{result.detection.summary}</p>
                </div>

                {result.detection.root_cause && (
                  <div>
                    <span className="font-semibold text-muted-foreground">Root Cause:</span>
                    <p className="mt-1 bg-muted/40 p-2.5 rounded-[var(--radius-sm)] border border-border text-foreground">
                      {result.detection.root_cause}
                    </p>
                  </div>
                )}

                {/* Remediation & FinOps */}
                <div>
                  <span className="font-semibold text-muted-foreground">Formulated Action:</span>
                  <p className="mt-1 font-medium text-foreground">{result.remediation.action_required}</p>
                </div>

                {result.finops_guardrail && (
                  <div className="rounded-[var(--radius-sm)] border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-[var(--status-warning-text)]">
                    <div className="flex items-center gap-1.5 font-bold">
                      <ShieldCheck className="h-4 w-4" />
                      FinOps Guardrail Applied:
                    </div>
                    <RemediationList text={result.finops_guardrail} />
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
                <Workflow className="h-10 w-10 text-muted-foreground/30 mb-2" />
                <p className="text-xs">Provide a log file or telemetry sample to run automated routing and root cause synthesis.</p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};
