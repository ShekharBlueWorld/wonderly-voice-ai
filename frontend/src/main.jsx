import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AudioLines, MessageSquare, Users, CalendarDays, BarChart3, Layers, Mic, MicOff, Send, Volume2, VolumeX, Zap, Clock3, CheckCircle2, Circle, Home, Settings, Square, Sparkles} from 'lucide-react';
import './style.css';
const API='http://127.0.0.1:8000';
const welcome="Hi! I'm Shekhar AI, your virtual remodeling consultant. Are you thinking about renovating your kitchen or bathroom?";
function App(){
 const [messages,setMessages]=useState([{role:'assistant',content:welcome}]);
 const [input,setInput]=useState('');const [busy,setBusy]=useState(false);
 const [speaking,setSpeaking]=useState(false);const [listening,setListening]=useState(false);
 const [muted,setMuted]=useState(false);const [llm,setLlm]=useState(null);const [tts,setTts]=useState(null);
 const [lead,setLead]=useState({});const [error,setError]=useState('');
 const audio=useRef(null);const recognition=useRef(null);const bottom=useRef(null);
 useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'});},[messages]);
 async function send(text=input){
  text=text.trim();if(!text||busy)return;
  setError('');setInput('');setBusy(true);
  const history=messages.map(m=>({role:m.role,content:m.content}));
  setMessages(prev=>[...prev,{role:'user',content:text}]);
  try{
   const response=await fetch(API+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,history})});
   const data=await response.json();if(!response.ok)throw Error(data.detail||'Chat failed');
   setMessages(prev=>[...prev,{role:'assistant',content:data.reply}]);setLlm(data.llm_ms);setLead(data.lead);
   if(!muted)await playSpeech(data.reply);
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 async function playSpeech(text){
  const start=performance.now();
  const response=await fetch(API+'/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  if(!response.ok){const data=await response.json();throw Error(data.detail||'Voice failed');}
  const blob=await response.blob();setTts(Math.round(performance.now()-start));
  const url=URL.createObjectURL(blob);const player=new Audio(url);audio.current=player;
  setSpeaking(true);player.onended=()=>{setSpeaking(false);URL.revokeObjectURL(url)};
  player.onerror=()=>{setSpeaking(false);URL.revokeObjectURL(url)};
  try{await player.play();}catch(e){setSpeaking(false);URL.revokeObjectURL(url);throw e;}
 }
 function toggleMic(){
  if(listening){recognition.current?.stop();setListening(false);return;}
  const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SpeechRecognition){setError('Microphone transcription currently requires Chrome. Local Whisper integration is next.');return;}
  const rec=new SpeechRecognition();recognition.current=rec;rec.lang='en-US';rec.interimResults=false;rec.continuous=false;
  rec.onresult=e=>{const text=e.results[0][0].transcript;setInput(text);};
  rec.onend=()=>setListening(false);rec.onerror=e=>{setError('Microphone: '+e.error);setListening(false)};
  try{rec.start();setListening(true);}catch(e){setError(e.message);}
 }
 const checks=[['Project type',lead.project],['Budget',lead.budget],['Timeline',lead.timeline],['Location',lead.location],['Consultation',null]];
 const progress=Math.round(checks.filter(x=>x[1]).length/checks.length*100);
 const status=listening?'Listening':speaking?'Speaking':busy?'Thinking':'Ready';
 return <div className="shell">
 <aside className="sidebar"><div className="brand"><div className="brandmark"><Home size={28}/></div><div><b>Wonderly</b><small>Voice AI</small></div></div>
 <nav>{[[MessageSquare,'Conversation'],[Users,'Leads'],[CalendarDays,'Appointments'],[BarChart3,'Performance'],[Layers,'AI Architecture']].map(([Icon,label],i)=><div className={'navitem '+(i===0?'active':'')} key={label}><Icon size={20}/>{label}</div>)}</nav>
 <div className="sidebarfoot"><div className="kitchen">✦ Dream kitchens start here</div><p>AI-powered home remodeling sales assistant</p><small>Demo built by Shekhar Venkat</small></div></aside>
 <main className="center"><section className="hero"><div className="heroavatar"><img src="/shekhar-avatar.jpg" onError={e=>{e.currentTarget.style.display='none'}} alt="Shekhar avatar"/><div className={'mini-wave '+(speaking?'live':'')}>{Array.from({length:15},(_,i)=><i key={i}/>)}</div></div><div className="herotext"><div className="eyebrow"><Sparkles size={14}/> AI SALES CONSULTANT</div><h1>Hi, I'm <span>Shekhar</span> 👋</h1><h2>Your AI remodeling consultant</h2><p>Let's plan your kitchen or bathroom renovation, explore options, and request a consultation.</p><div className="chips">{['Kitchen remodel','Bathroom remodel','Discuss budget','Schedule consultation'].map(x=><button key={x} onClick={()=>setInput(x)}>{x}</button>)}</div></div></section>
 <section className="conversation"><div className="conversationhead"><div><b>Live Conversation</b><small>Talk naturally with Shekhar AI</small></div><span className="online"><span className="dot"/> {status}</span></div>
 <div className="messages">{messages.map((m,i)=><div key={i} className={'msg '+m.role}><div className="msgavatar">{m.role==='assistant'?<img src="/shekhar-avatar.jpg" onError={e=>e.currentTarget.style.display='none'}/>:<Users size={18}/>}</div><div className="bubble">{m.content}</div></div>)}{busy&&<div className="thinking">Shekhar AI is thinking<span className="dots">...</span></div>}<div ref={bottom}/></div>
 <div className={'voicezone '+(listening||speaking?'animated':'')}><div className="wave">{Array.from({length:31},(_,i)=><i key={i} style={{'--n':i}}/>)}</div><button className={'micbutton '+(listening?'recording':'')} onClick={toggleMic} aria-label={listening?'Stop listening':'Start microphone'}>{listening?<MicOff size={31}/>:<Mic size={31}/>}</button><div className="voicecaption">{listening?'Listening — speak now':speaking?'Shekhar AI is speaking':busy?'Generating response...':'Tap microphone to speak'}</div><small>Prototype speech recognition uses your browser's service</small></div>
 {error&&<div className="error">{error}</div>}
 <form className="composer" onSubmit={e=>{e.preventDefault();send()}}><input placeholder="Ask about your remodeling project..." value={input} onChange={e=>setInput(e.target.value)}/><button type="button" className="sound" onClick={()=>{setMuted(!muted);if(audio.current&&!muted){audio.current.pause();setSpeaking(false)}}}>{muted?<VolumeX size={21}/>:<Volume2 size={21}/>}</button><button type="submit" disabled={busy||!input.trim()} className="send"><Send size={21}/></button></form>
 </section></main>
 <aside className="insights"><div className="topbar"><span className="online"><span className="dot"/> Shekhar Online</span><Settings size={19}/></div>
 <div className="panel"><h3>Live Performance</h3><div className="metrics"><div><Zap size={24}/><small>AI response</small><strong>{llm===null?'—':(llm/1000).toFixed(2)+'s'}</strong></div><div><AudioLines size={24}/><small>Speech (TTS)</small><strong>{tts===null?'—':(tts/1000).toFixed(2)+'s'}</strong></div><div><Clock3 size={24}/><small>Generation total</small><strong>{llm===null||tts===null?'—':((llm+tts)/1000).toFixed(2)+'s'}</strong></div></div><p className="metricnote">Measured locally; excludes playback duration and network speech recognition.</p></div>
 <div className="panel"><h3>Lead Qualification</h3><div className="qualification"><div className="ring" style={{'--progress':progress}}><div>{progress}%</div></div><div className="checklist">{checks.map(([label,value])=><div key={label}>{value?<CheckCircle2 size={19} color="#16a34a"/>:<Circle size={19} color="#9eacc3"/>}<span>{label}{value?': '+value:''}</span></div>)}</div></div><p className="metricnote">Prototype extraction from chat text; verify lead details before scheduling.</p></div>
 <div className="panel next"><div className="nextlabel"><CalendarDays size={20}/> NEXT BEST ACTION</div><h3>Request a Consultation</h3><p>Qualify the homeowner's project and offer a design consultation.</p><button onClick={()=>setInput('I would like to request a design consultation. What information do you need?')}><CalendarDays size={18}/> Discuss Appointment</button><small>Demo only — no live booking is performed</small></div>
 </aside></div>;
}
createRoot(document.getElementById('root')).render(<App/>);
