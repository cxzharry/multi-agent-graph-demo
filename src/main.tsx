import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType, type NodeProps, type Node, type Edge} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {Bot, Brain, Code2, FlaskConical, CheckCircle2, Radio, RotateCcw, Play, Pause, Wifi, WifiOff} from 'lucide-react';
import './style.css';

type Status='pending'|'running'|'waiting'|'done'|'error';
type Mode='live'|'replay';
type ConnectionState='connecting'|'connected'|'disconnected'|'error';
type AgentData={label:string, role:string, session:string, activity:string, status:Status, icon:'brain'|'code'|'test'|'bot'};
type StreamEvent={graphId?:string,nodeId?:string,type?:string,status?:Status,activity?:string,sessionId?:string,agent?:string,label?:string,timestamp?:string|number,payload?:Record<string, unknown>};
type TimelineEvent={id:string,t?:number,node:string,type:string,status?:Status,activity:string,label:string,timestamp:string,source:'live'|'replay'};

const steps=[
 {t:0,node:'bibi',status:'running',activity:'Receiving user task → drafting execution graph',event:'Bibi starts orchestration'},
 {t:1,node:'codex',status:'running',activity:'Generating React Flow graph UI',event:'Bibi delegates implementation to Codex'},
 {t:2,node:'bibi',status:'waiting',activity:'Waiting on worker sessions',event:'Orchestrator is waiting on Codex'},
 {t:3,node:'codex',status:'done',activity:'Demo code complete',event:'Codex reports implementation complete'},
 {t:4,node:'claude',status:'running',activity:'Running build + visual QC checklist',event:'Bibi delegates QC to Claude'},
 {t:5,node:'claude',status:'done',activity:'Build passed, layout verified',event:'Claude returns test results'},
 {t:6,node:'bibi',status:'done',activity:'Aggregating final answer for Harry',event:'Bibi completes run'},
];
const nodeAliases:Record<string,string>={bibi:'bibi',orchestrator:'bibi',codex:'codex',claude:'claude',final:'final',delivery:'final'};
const baseNodes: Node<AgentData>[]=[
 {id:'bibi', type:'agent', position:{x:420,y:60}, data:{label:'Bibi',role:'Orchestrator',session:'tg:1786660169',activity:'Queued',status:'pending',icon:'brain'}},
 {id:'codex', type:'agent', position:{x:120,y:300}, data:{label:'Codex',role:'Implementation Agent',session:'codex:pane-01',activity:'Pending delegation',status:'pending',icon:'code'}},
 {id:'claude', type:'agent', position:{x:720,y:300}, data:{label:'Claude',role:'Test / QC Agent',session:'claude:pane-01',activity:'Pending handoff',status:'pending',icon:'test'}},
 {id:'final', type:'agent', position:{x:420,y:520}, data:{label:'Final Demo',role:'Delivery Node',session:'artifact:demo',activity:'Waiting for agents',status:'pending',icon:'bot'}},
];
function normalizeNodeId(event:StreamEvent){
 const raw=String(event.nodeId||event.agent||event.label||'').toLowerCase().trim();
 return nodeAliases[raw] || nodeAliases[raw.replace(/\s+/g,'-')] || (baseNodes.some(n=>n.id===raw)?raw:'');
}
function normalizeStatus(status?:string):Status|undefined{
 if(status==='pending'||status==='running'||status==='waiting'||status==='done'||status==='error') return status;
 if(status==='complete'||status==='completed'||status==='success') return 'done';
 if(status==='active'||status==='started') return 'running';
 return undefined;
}
function liveToTimeline(event:StreamEvent, i:number):TimelineEvent{
 const node=normalizeNodeId(event) || 'bibi';
 const status=normalizeStatus(event.status);
 const label=event.label || event.type || `${node} update`;
 const activity=event.activity || (typeof event.payload?.message==='string'?event.payload.message:label);
 return {id:`live-${Date.now()}-${i}`,node,type:event.type||'event',status,activity,label,timestamp:String(event.timestamp||new Date().toISOString()),source:'live'};
}
function Icon({kind}:{kind:AgentData['icon']}){const C=kind==='brain'?Brain:kind==='code'?Code2:kind==='test'?FlaskConical:Bot; return <C size={22}/>}
function AgentNode({data}:NodeProps<Node<AgentData>>){return <div className={`agent ${data.status}`}><Handle type="target" position={Position.Top}/><div className="shine"/><div className="top"><div className="avatar"><Icon kind={data.icon}/></div><div><div className="label">{data.label}</div><div className="role">{data.role}</div></div><span className="pill">{data.status}</span></div><div className="activity">{data.activity}</div><div className="session"><Radio size={12}/>{data.session}</div><Handle type="source" position={Position.Bottom}/></div>}
const nodeTypes={agent:AgentNode};

function App(){
 const [tick,setTick]=useState(0);
 const [playing,setPlaying]=useState(true);
 const [mode,setMode]=useState<Mode>('replay');
 const [connection,setConnection]=useState<ConnectionState>('disconnected');
 const [liveNodes,setLiveNodes]=useState<Node<AgentData>[]>(baseNodes);
 const [liveEvents,setLiveEvents]=useState<TimelineEvent[]>([]);

 useEffect(()=>{if(mode!=='replay'||!playing)return; const id=setInterval(()=>setTick(t=>(t+1)%7),1400); return()=>clearInterval(id)},[playing,mode]);
 useEffect(()=>{
  if(mode!=='live'){setConnection('disconnected'); return;}
  setConnection('connecting');
  const es=new EventSource('/stream');
  let count=0;
  const apply=(raw:MessageEvent)=>{
   try{
    const parsed:StreamEvent=JSON.parse(raw.data);
    const event=liveToTimeline(parsed,count++);
    setLiveEvents(prev=>[event,...prev].slice(0,24));
    const nodeId=normalizeNodeId(parsed);
    if(!nodeId) return;
    setLiveNodes(prev=>prev.map(n=>n.id===nodeId?{...n,data:{...n.data,label:parsed.label||n.data.label,session:parsed.sessionId||n.data.session,status:normalizeStatus(parsed.status)||n.data.status,activity:event.activity||n.data.activity}}:n));
   }catch(err){
    const parseEvent:TimelineEvent={id:`parse-${Date.now()}`,node:'stream',type:'error',status:'error',activity:'Unable to parse incoming SSE event',label:'Malformed stream event',timestamp:new Date().toISOString(),source:'live'};
    setLiveEvents(prev=>[parseEvent,...prev].slice(0,24));
   }
  };
  es.onopen=()=>setConnection('connected');
  es.onerror=()=>setConnection(es.readyState===EventSource.CLOSED?'disconnected':'error');
  es.onmessage=apply;
  es.addEventListener('agent',apply as EventListener);
  es.addEventListener('graph',apply as EventListener);
  return()=>es.close();
 },[mode]);

 const replayEvents=steps.filter(s=>s.t<=tick).slice(-6).reverse().map((s,i):TimelineEvent=>({id:`replay-${s.t}-${i}`,t:s.t,node:s.node,type:'replay',status:s.status as Status,activity:s.activity,label:s.event,timestamp:`t+${s.t}s`,source:'replay'}));
 const nodes=useMemo(()=>mode==='live'?liveNodes:baseNodes.map(n=>{let data={...n.data}; for(const s of steps.filter(x=>x.t<=tick&&x.node===n.id)){data.status=s.status as Status; data.activity=s.activity} if(n.id==='final'&&tick>=6){data.status='done'; data.activity='Packaged as runnable React Flow demo'} return {...n,data}}),[tick,mode,liveNodes]);
 const events=mode==='live'?liveEvents:replayEvents;
 const active=mode==='live'?(events[0]?.node||'idle'):([...steps].reverse().find(s=>s.t===tick)?.node||'idle');
 const edgeLit=(id:string)=>mode==='live'?nodes.find(n=>n.id===id)?.data.status==='running'||nodes.find(n=>n.id===id)?.data.status==='done':false;
 const edges:Edge[]=[
  {id:'e1',source:'bibi',target:'codex',animated:mode==='replay'?tick>=1&&tick<=3:edgeLit('codex'),markerEnd:{type:MarkerType.ArrowClosed},className:mode==='replay'?(tick>=1?'lit':''):(edgeLit('codex')?'lit':'')},
  {id:'e2',source:'bibi',target:'claude',animated:mode==='replay'?tick>=4&&tick<=5:edgeLit('claude'),markerEnd:{type:MarkerType.ArrowClosed},className:mode==='replay'?(tick>=4?'lit':''):(edgeLit('claude')?'lit':'')},
  {id:'e3',source:'codex',target:'final',animated:mode==='replay'?tick>=3&&tick<6:edgeLit('final'),markerEnd:{type:MarkerType.ArrowClosed},className:mode==='replay'?(tick>=3?'lit':''):(edgeLit('final')?'lit':'')},
  {id:'e4',source:'claude',target:'final',animated:mode==='replay'?tick>=5:edgeLit('final'),markerEnd:{type:MarkerType.ArrowClosed},className:mode==='replay'?(tick>=5?'lit':''):(edgeLit('final')?'lit':'')},
 ];
 const reset=()=>{setTick(0); setLiveNodes(baseNodes); setLiveEvents([])};
 return <main><div className="hero"><div><p className="eyebrow">REALTIME MULTI-AGENT EXECUTION GRAPH</p><h1>Hermes Graph Demo</h1><p className="sub">Watch the process move between Bibi → Codex → Claude in near realtime.</p></div><div className="buttons"><div className={`badge ${connection}`} title="/stream SSE connection">{mode==='live'?(connection==='connected'?<Wifi size={16}/>:<WifiOff size={16}/>):<CheckCircle2 size={16}/>} {mode==='live'?connection:'replay ready'}</div><button className={mode==='live'?'selected':''} onClick={()=>setMode(mode==='live'?'replay':'live')}>{mode==='live'?'Live':'Replay'}</button><button onClick={()=>setPlaying(!playing)} disabled={mode==='live'}>{playing?<Pause size={16}/>:<Play size={16}/>} {playing?'Pause':'Play'}</button><button onClick={reset}><RotateCcw size={16}/> Reset</button></div></div><section className="layout"><div className="canvas"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView proOptions={{hideAttribution:true}}><Background color="#2b3555" gap={26}/><Controls/><MiniMap pannable zoomable nodeColor={(n)=>n.data.status==='running'?'#38bdf8':n.data.status==='done'?'#22c55e':n.data.status==='error'?'#ef4444':'#64748b'}/></ReactFlow><div className="active">Current active node: <b>{active}</b></div></div><aside><h2>Event Timeline</h2>{events.length===0&&<div className="empty">Waiting for {mode==='live'?'/stream events':'replay ticks'}…</div>}{events.map((e)=><div className={`evt ${e.status||''}`} key={e.id}><span>{e.timestamp}</span><p>{e.label}</p><small>{e.node} · {e.activity}</small></div>)}</aside></section></main>}
createRoot(document.getElementById('root')!).render(<App/>);
