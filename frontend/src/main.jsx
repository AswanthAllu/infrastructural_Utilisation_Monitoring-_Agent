import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, ArrowRight, CheckCircle2, ClipboardCheck, Cpu, HardDrive, LoaderCircle, MemoryStick, Menu, RefreshCw, Server, ShieldCheck, TriangleAlert, Wrench, X, XCircle } from 'lucide-react'
import { createRoot } from 'react-dom/client'
import logo from '../logo.jpg'
import './styles.css'

const agents = [
  { key: 'cpu', label: 'CPU monitoring agent', icon: Cpu, metric: 'processor health', endpoint: '/api/cpu/analyze' },
  { key: 'disk', label: 'Disk utilization agent', icon: HardDrive, metric: 'storage utilization', endpoint: '/api/disk/analyze' },
  { key: 'memory', label: 'Memory utilization agent', icon: MemoryStick, metric: 'RAM utilization', endpoint: '/api/memory/analyze' },
]
const pretty = value => String(value || 'READY').replaceAll('_', ' ').toLowerCase().replace(/(^|\s)\S/g, x => x.toUpperCase())
const severityOf = result => result?.detection?.severity || result?.diagnosis?.severity || 'READY'
const severityClass = value => String(value || 'ready').toLowerCase()
const usageOf = result => Number(result?.current_usage_percent ?? result?.peak_usage_percent ?? 0)
const remediationPoints = value => {
  if (!value) return []
  const text = String(value).trim()
  const points = text.split(/\n+|(?<=[.;])\s+(?=[A-Z])/).map(point => point.replace(/^[-*•\d.)]+\s*/, '').trim()).filter(Boolean)
  return points.length ? points : [text]
}

function HealthCard({ title, value, status, icon: Icon }) {
  return <div className={`health-card ${severityClass(status)}`}><div className="health-card-title"><Icon size={19}/><strong>{title}</strong></div><div className="health-value">{value === null ? '—' : `${value.toFixed(1)}%`}</div><span className={`health-badge ${severityClass(status)}`}>{pretty(status)}</span></div>
}

function ResponseCard({ agent, state, result, onRun }) {
  const Icon = agent.icon, severity = severityOf(result), plans = Array.isArray(result?.remediation_plans) ? result.remediation_plans : []
  return <article className={`response-card ${state}`}>
    <div className="response-card-head"><span className="response-icon"><Icon size={20}/></span><span className={`severity ${severityClass(severity)}`}><span/>{state === 'loading' ? 'Running' : state === 'error' ? 'Error' : pretty(severity)}</span></div>
    <h3>{agent.label}</h3><p className="agent-purpose">Monitors <strong>{agent.metric}</strong></p>
    {state === 'loading' && <div className="response-loading"><LoaderCircle className="spin" size={18}/> Loading configured telemetry and analyzing each service...</div>}
    {state === 'error' && <div className="response-error"><XCircle size={15}/>{result}</div>}
    {state === 'idle' && <p className="response-muted">Ready to fetch live VM telemetry.</p>}
    {state === 'success' && <div className="agent-result-fields">
      <div className="metric-pair"><div><span>Peak usage</span><strong>{result?.peak_usage_percent ?? '—'}%</strong></div><div><span>Current usage</span><strong>{result?.current_usage_percent ?? '—'}%</strong></div></div>
      <p className="data-source"><strong>Data source:</strong> {result?.data_source || 'VM telemetry API'} · {result?.total_records_analyzed || 0} records</p>
      <div className="plans-heading"><ClipboardCheck size={16}/> Remediation plans <span>{plans.length}</span></div>
      {plans.length ? <div className="plan-list">{plans.map((plan, index) => <section className={`plan-card severity-panel-${severityClass(plan.severity || severity)}`} key={plan.plan_id || index}>
        <div className="plan-header"><div className="plan-number">{String(index + 1).padStart(2, '0')}</div><div><span className="plan-kicker">Service remediation</span><h4>{plan.service_name || result?.service_name || result?.hostname || 'VM host'}</h4></div><span className={`plan-severity ${severityClass(plan.severity || severity)}`}>{pretty(plan.severity || severity)}</span></div>
        <div className="plan-section"><div className="plan-section-title"><TriangleAlert size={15}/> Root cause</div><p>{plan.root_cause || '—'}</p></div>
        <div className="plan-section remediation-action"><div className="plan-section-title"><Wrench size={15}/> Action required</div><ul className="remediation-points">{remediationPoints(plan.action_required || 'Continue monitoring.').map((point, pointIndex) => <li key={pointIndex}><strong>{point}</strong></li>)}</ul></div>
        {plan.preventive_guardrail && <div className="plan-section guardrail"><div className="plan-section-title"><ShieldCheck size={15}/> Preventive guardrail</div><ul className="remediation-points">{remediationPoints(plan.preventive_guardrail).map((point, pointIndex) => <li key={pointIndex}>{point}</li>)}</ul></div>}
      </section>)}</div> : <p className="response-muted">No remediation required.</p>}
    </div>}
    <button className="agent-run-button" onClick={() => onRun(agent)} disabled={state === 'loading'}>{state === 'loading' ? <><LoaderCircle className="spin" size={14}/> Running</> : state === 'success' ? <>Refresh live data <RefreshCw size={14}/></> : <>Run {agent.key} <ArrowRight size={14}/></>}</button>
  </article>
}

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [states, setStates] = useState(Object.fromEntries(agents.map(a => [a.key, 'idle'])))
  const [results, setResults] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [view, setView] = useState('dashboard')

  const runAgent = useCallback(async agent => {
    setStates(s => ({ ...s, [agent.key]: 'loading' }))
    try {
      const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 180000)
      const response = await fetch(agent.endpoint, { headers: { Accept: 'application/json' }, signal: controller.signal })
      clearTimeout(timer)
      const body = await response.text(); let data
      try { data = body ? JSON.parse(body) : {} } catch { data = { error: body || 'Invalid backend response.' } }
      if (!response.ok || data.success === false) throw Error(data.detail || data.error || `${agent.label} failed.`)
      setResults(r => ({ ...r, [agent.key]: data })); setStates(s => ({ ...s, [agent.key]: 'success' })); setLastUpdated(new Date())
    } catch (error) { setResults(r => ({ ...r, [agent.key]: error.name === 'AbortError' ? 'VM analysis timed out after 3 minutes.' : error.message })); setStates(s => ({ ...s, [agent.key]: 'error' })) }
  }, [])

  useEffect(() => { agents.forEach(runAgent) }, [runAgent])
  const complete = Object.values(states).filter(x => x === 'success').length
  const health = agents.map(agent => ({ agent, result: results[agent.key], value: states[agent.key] === 'success' ? usageOf(results[agent.key]) : null, status: states[agent.key] === 'error' ? 'CRITICAL' : states[agent.key] === 'success' ? severityOf(results[agent.key]) : 'READY' }))
  const incidents = useMemo(() => health.filter(item => item.status !== 'READY' && item.status !== 'LOW').map(item => ({ ...item, diagnosis: item.result?.diagnosis?.root_cause || item.result?.detection?.summary || 'Resource threshold requires attention.' })), [health])
  const services = useMemo(() => [...new Map(health.flatMap(item => (item.result?.records || []).map(record => [record.service_name || record.process_name || record.hostname, { name: record.service_name || record.process_name || record.hostname, status: item.status }]))).values()], [health])
  const refreshAll = () => agents.forEach(runAgent)

  return <div className={`app-shell ${sidebarOpen ? 'sidebar-is-open' : ''}`}><button className="menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Menu size={22}/></button><aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}><div className="sidebar-head"><a className="brand" href="#top"><img src={logo} alt="Dashboard logo"/></a><button className="close-sidebar" onClick={() => setSidebarOpen(false)}><X size={20}/></button></div><nav><a href="#overview" className={view === 'dashboard' ? 'active' : ''} onClick={() => { setView('dashboard'); setSidebarOpen(false) }}>Dashboard</a><a href="#responses" className={view === 'agents' ? 'active' : ''} onClick={() => { setView('agents'); setSidebarOpen(false) }}>Agents</a></nav><div className="sidebar-status"><span className="pulse"/> VM monitoring</div></aside><div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)}/><header className="topbar"><a className="topbar-brand" href="#top"><img src={logo} alt="Reliability dashboard logo"/></a></header><main className="page-content" id="top">{view === 'dashboard' && <section className="responses-section" id="overview"><div className="section-heading"><div><h1>Infrastructure Utilization Monitoring Agents</h1><p className="section-description">Live infrastructure health, incidents, trends, and remediation from the VM telemetry API.</p></div><button className="refresh-all" onClick={refreshAll}><RefreshCw size={16}/> Refresh all</button></div><div className="connection-strip"><span className={`connection-dot ${complete === 3 ? 'connected' : 'waiting'}`}/><strong>{complete === 3 ? 'VM telemetry connected' : 'Waiting for VM telemetry'}</strong><span>Data source: VM telemetry API</span><span>Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}</span></div><div className="health-grid">{health.map(({ agent, value, status }) => <HealthCard key={agent.key} title={agent.key.toUpperCase()} value={value} status={status} icon={agent.icon}/>)}</div><div className="summary-grid"><div className="summary-panel"><div className="panel-heading"><Activity size={18}/> Usage trend</div><div className="trend-bars">{health.map(item => <div className="trend-item" key={item.agent.key}><span>{item.agent.key}</span><div className="trend-track"><i className={severityClass(item.status)} style={{ width: `${Math.min(item.value || 0, 100)}%` }}/></div><strong>{item.value === null ? '—' : `${item.value.toFixed(1)}%`}</strong></div>)}</div><small>Trend baseline uses the latest live VM history returned by each agent.</small></div><div className="summary-panel" id="incidents"><div className="panel-heading"><TriangleAlert size={18}/> Active incidents <b>{incidents.length}</b></div>{incidents.length ? incidents.map(item => <div className={`incident-row ${severityClass(item.status)}`} key={item.agent.key}><strong>{item.agent.key.toUpperCase()} · {pretty(item.status)}</strong><span>{item.diagnosis}</span></div>) : <p className="empty-state"><CheckCircle2 size={18}/> No active incidents detected.</p>}</div><div className="summary-panel"><div className="panel-heading"><Server size={18}/> Service health</div>{services.length ? services.slice(0, 8).map(service => <div className="service-row" key={service.name}><strong>{service.name}</strong><span className={`health-badge ${severityClass(service.status)}`}>{pretty(service.status)}</span></div>) : <p className="empty-state">Service metadata will appear when supplied by the VM API.</p>}</div></div></section>} {view === 'agents' && <section className="responses-section" id="responses"><div className="section-heading"><div><h2>Agents</h2><p className="section-description">Detailed findings and clear remediation actions.</p></div><span className="completion-count"><CheckCircle2 size={15}/> {complete} of 3 complete</span></div><div className="response-grid">{agents.map(agent => <ResponseCard key={agent.key} agent={agent} state={states[agent.key]} result={results[agent.key]} onRun={runAgent}/>)}</div></section>}</main></div>
}
createRoot(document.getElementById('root')).render(<App />)
