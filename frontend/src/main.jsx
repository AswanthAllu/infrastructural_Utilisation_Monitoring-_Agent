import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowRight, CheckCircle2, Cpu, HardDrive, LoaderCircle, MemoryStick, Menu, X, XCircle } from 'lucide-react'
import logo from '../logo.jpg'
import './styles.css'

const agents = [
  { key: 'cpu', label: 'CPU monitoring agent', icon: Cpu, metric: 'processor health', endpoint: '/api/cpu/analyze' },
  { key: 'disk', label: 'Disc utilization agent', icon: HardDrive, metric: 'storage utilization', endpoint: '/api/disk/analyze' },
  { key: 'memory', label: 'Memory utilization agent', icon: MemoryStick, metric: 'RAM utilization', endpoint: '/api/memory/analyze' },
]
const text = value => !value ? 'No explanation was returned.' : typeof value === 'string' ? value : value.summary || value.reason || value.message || value.root_cause || value.diagnosis || value.explanation || value.description || JSON.stringify(value)
const label = value => String(value || 'Ready').replaceAll('_', ' ').toLowerCase().replace(/(^|\s)\S/g, x => x.toUpperCase())

function ResponseCard({ agent, state, result, onRun }) {
  const Icon = agent.icon; const detection = result?.detection || {}; const diagnosis = result?.diagnosis || {}
  const severity = detection.severity || diagnosis.severity || 'READY'; const plans = Array.isArray(result?.remediation_plans) ? result.remediation_plans : []
  return <article className={`response-card ${state}`}><div className="response-card-head"><span className="response-icon"><Icon size={18}/></span><span className={`severity ${String(severity).toLowerCase()}`}><span/>{state === 'loading' ? 'Running' : state === 'error' ? 'Error' : label(severity)}</span></div><h3>{agent.label}</h3><p className="agent-purpose">Monitors {agent.metric}</p>
    {state === 'loading' && <div className="response-loading"><LoaderCircle className="spin" size={18}/> Preparing analysis... response will be available in about 40 seconds.</div>}
    {state === 'error' && <div className="response-error"><XCircle size={15}/>{result}</div>}
    {state === 'idle' && <p className="response-muted">Ready to start this agent.</p>}
     {state === 'success' && <div className="agent-result-fields"><div className="metric-pair"><div><span>Peak usage</span><strong>{result?.peak_usage_percent ?? '—'}%</strong></div><div><span>Current usage</span><strong>{result?.current_usage_percent ?? '—'}%</strong></div></div><div className="plans-heading">Remediation plans</div>{plans.length ? <div className={agent.key === 'cpu' ? 'cpu-response-scroll' : ''}>{plans.map((plan, index) => <div className="plan-card" key={plan.plan_id || index}><span className={`plan-severity ${String(plan.severity || severity).toLowerCase()}`}>{plan.severity || severity}</span><div><span className="plan-label">Service</span><p className="service-name">{plan.service_name || result?.service_name || 'Unknown service'}</p></div><div><span className="plan-label">Root cause</span><p>{plan.root_cause || '—'}</p></div><div><span className="plan-label">Action required</span><p>{plan.action_required || '—'}</p></div></div>)}</div> : <p className="response-muted">No remediation plans returned.</p>}</div>}
    <button className="agent-run-button" onClick={() => onRun(agent)} disabled={state === 'loading'}>{state === 'loading' ? <><LoaderCircle className="spin" size={14}/> Running</> : state === 'success' ? <>Run again <ArrowRight size={14}/></> : <>Run {agent.label.split(' ')[0]} <ArrowRight size={14}/></>}</button>
  </article>
}
function App() {
  const [sidebarOpen,setSidebarOpen]=useState(false), [states,setStates]=useState(Object.fromEntries(agents.map(a=>[a.key,'idle']))), [results,setResults]=useState({})
  async function runAgent(agent) { setStates(s=>({...s,[agent.key]:'loading'})); try { await new Promise(resolve=>setTimeout(resolve,40000)); const c=new AbortController(); const timer=setTimeout(()=>c.abort(),180000); const response=await fetch(`${agent.endpoint}?use_local_file=true&force_fetch=false`,{headers:{Accept:'application/json'},signal:c.signal}); clearTimeout(timer); const body=await response.text(); let data; try{data=body?JSON.parse(body):{}}catch{data={error:body||'Invalid backend response.'}} if(!response.ok||data.success===false) throw Error(data.detail||data.error||`The ${agent.label} returned an error.`); setResults(r=>({...r,[agent.key]:data})); setStates(s=>({...s,[agent.key]:'success'})) } catch(e) { setResults(r=>({...r,[agent.key]:e.name==='AbortError'?`${agent.label} timed out after 3 minutes.`:e.message})); setStates(s=>({...s,[agent.key]:'error'})) } }
  const complete=Object.values(states).filter(x=>x==='success').length
  return <div className={`app-shell ${sidebarOpen?'sidebar-is-open':''}`}><button className="menu-button" onClick={()=>setSidebarOpen(true)} aria-label="Open navigation"><Menu size={22}/></button><aside className={`sidebar ${sidebarOpen?'open':''}`}><div className="sidebar-head"><a className="brand" href="#top"><img src={logo} alt="Dashboard logo"/></a><button className="close-sidebar" onClick={()=>setSidebarOpen(false)}><X size={20}/></button></div><nav><a href="#responses" onClick={()=>setSidebarOpen(false)}>Agent responses</a></nav><div className="sidebar-status"><span className="pulse"/> Online</div></aside><div className="sidebar-backdrop" onClick={()=>setSidebarOpen(false)}/><header className="topbar"><a className="topbar-brand" href="#top"><img src={logo} alt="Reliability dashboard logo"/></a><span className="system-state"><i/> Online</span></header><main className="page-content" id="top"><section className="responses-section" id="responses"><div className="section-heading"><div><h1>Monitoring agents</h1><p className="section-description">Run each backend monitoring agent independently and review its response here.</p></div><span className="completion-count"><CheckCircle2 size={15}/> {complete} of 3 complete</span></div><div className="response-grid">{agents.map(agent=><ResponseCard key={agent.key} agent={agent} state={states[agent.key]} result={results[agent.key]} onRun={runAgent}/>)}</div></section></main></div>
}
createRoot(document.getElementById('root')).render(<App />)
