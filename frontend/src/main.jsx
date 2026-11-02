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
 const [ttsEngine,setTtsEngine]=useState(null);const [ttfa,setTtfa]=useState(null);const [samples,setSamples]=useState([]);const [turnDetect,setTurnDetect]=useState(null);const [stt,setStt]=useState(null);
 const turnStart=useRef(null);
 const [autoMode,setAutoMode]=useState(false);const [view,setView]=useState('Conversation');
 const autoRef=useRef(false),busyRef=useRef(false),speakingRef=useRef(false);
 const [mouth,setMouth]=useState(0),animationRef=useRef(null),audioContextRef=useRef(null);
 const messagesRef=useRef(messages);messagesRef.current=messages;
 const mutedRef=useRef(muted);mutedRef.current=muted;
 const recognitionActive=useRef(false);
 function startListening(){
  if(!autoRef.current||busyRef.current||speakingRef.current||recognitionActive.current)return;
  const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SpeechRecognition){setError('Chrome speech recognition is required for this prototype.');autoRef.current=false;setAutoMode(false);return;}
  const rec=new SpeechRecognition();recognition.current=rec;rec.lang='en-US';rec.interimResults=true;rec.continuous=false;
  rec.onstart=()=>{recognitionActive.current=true;setListening(true);turnStart.current=performance.now()};
  rec.onresult=e=>{let finalText='';for(let i=e.resultIndex;i<e.results.length;i++)if(e.results[i].isFinal)finalText+=e.results[i][0].transcript;
    if(finalText.trim()){setStt(Math.round(performance.now()-turnStart.current));rec.onend=null;rec.stop();recognitionActive.current=false;setListening(false);send(finalText.trim());}};
  rec.onerror=e=>{if(e.error!=='aborted'&&e.error!=='no-speech'){setError('Microphone: '+e.error);autoRef.current=false;setAutoMode(false)}};
  rec.onend=()=>{recognitionActive.current=false;setListening(false);if(autoRef.current&&!busyRef.current&&!speakingRef.current)startListening()};
  try{rec.start()}catch(e){recognitionActive.current=false;setError(e.message)}
 }
 function toggleAuto(){
  if(autoRef.current){autoRef.current=false;setAutoMode(false);recognition.current?.abort();recognitionActive.current=false;setListening(false);audio.current?.pause();speakingRef.current=false;setSpeaking(false);cancelAnimationFrame(animationRef.current);setMouth(0);}
  else{autoRef.current=true;setAutoMode(true);startListening();}
 }

 const audio=useRef(null);const recognition=useRef(null);const bottom=useRef(null);
 useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'});},[messages]);
 async function send(text=input){
  text=text.trim();if(!text||busyRef.current)return;
  busyRef.current=true;recognition.current?.abort();recognitionActive.current=false;setListening(false);
  setError('');setInput('');setBusy(true);setTts(null);setTtsEngine(null);setTtfa(null);
  const start=performance.now();
  const history=messagesRef.current.map(m=>({role:m.role,content:m.content}));
  setMessages(prev=>[...prev,{role:'user',content:text}]);
  try{
   const response=await fetch(API+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,history})});
   const data=await response.json();if(!response.ok)throw Error(data.detail||'Chat failed');
   setMessages(prev=>[...prev,{role:'assistant',content:data.reply}]);setLlm(data.llm_ms);setLead(data.lead);
   if(!mutedRef.current){await playSpeech(data.reply,start);}else{setSamples(prev=>[...prev.slice(-29),{llm:data.llm_ms,ttfa:null}]);}
  }catch(e){const msg=e instanceof TypeError?'Cannot reach the local backend at http://127.0.0.1:8000. Restart FastAPI and check /api/health.':e.message;setError(msg);autoRef.current=false;setAutoMode(false);recognition.current?.abort();recognitionActive.current=false;setListening(false);}finally{setBusy(false);busyRef.current=false;if(autoRef.current&&!speakingRef.current)startListening();}
 }
 async function playSpeech(text,turnStartTime){
  const start=performance.now();
  const response=await fetch(API+'/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  if(!response.ok){const data=await response.json();throw Error(data.detail||'Voice failed');}
  const blob=await response.blob();setTts(Math.round(performance.now()-start));
  const synth=Number(response.headers.get('X-TTS-Synthesis-Ms'));if(Number.isFinite(synth)&&synth>0)setTtsEngine(synth);
  const url=URL.createObjectURL(blob);const player=new Audio(url);audio.current=player;
  setSpeaking(true);speakingRef.current=true;player.onended=()=>{setSpeaking(false);speakingRef.current=false;setMouth(0);cancelAnimationFrame(animationRef.current);URL.revokeObjectURL(url);if(autoRef.current&&!busyRef.current)startListening()};
  player.onerror=()=>{setSpeaking(false);speakingRef.current=false;setMouth(0);cancelAnimationFrame(animationRef.current);URL.revokeObjectURL(url);if(autoRef.current&&!busyRef.current)startListening()};
  try{
   if(!audioContextRef.current)audioContextRef.current=new (window.AudioContext||window.webkitAudioContext)();
   const context=audioContextRef.current,source=context.createMediaElementSource(player),analyser=context.createAnalyser();
   analyser.fftSize=512;source.connect(analyser);analyser.connect(context.destination);await context.resume();
   const levels=new Uint8Array(analyser.frequencyBinCount);
   const animate=()=>{analyser.getByteFrequencyData(levels);let sum=0;for(let i=2;i<90;i++)sum+=levels[i];
     setMouth(Math.max(0,Math.min(1,(sum/88-12)/70)));animationRef.current=requestAnimationFrame(animate)};
   animate();await player.play();const first= Math.round(performance.now()-turnStartTime);setTtfa(first);setSamples(prev=>[...prev.slice(-29),{llm:Math.round(start-turnStartTime),ttfa:first}]);}catch(e){setSpeaking(false);speakingRef.current=false;setMouth(0);cancelAnimationFrame(animationRef.current);URL.revokeObjectURL(url);throw e;}
 }
 function toggleMic(){
  if(listening){recognition.current?.stop();setListening(false);return;}
  const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SpeechRecognition){setError('Microphone transcription currently requires Chrome. Local Whisper integration is next.');return;}
  const rec=new SpeechRecognition();recognition.current=rec;rec.lang='en-US';rec.interimResults=false;rec.continuous=false;
  rec.onresult=e=>{const text=e.results[0][0].transcript;setInput(text);if(turnStart.current)setStt(Math.round(performance.now()-turnStart.current));};
  rec.onend=()=>{setListening(false);setTurnDetect(null);};rec.onerror=e=>{setError('Microphone: '+e.error);setListening(false)};
  try{turnStart.current=performance.now();rec.start();setListening(true);}catch(e){setError(e.message);}
 }
 const checks=[['Kitchen or bathroom?',lead.project],['What is your budget?',lead.budget],['What needs remodeling?',lead.scope],['When do you want to start?',lead.timeline],['Where is the property?',lead.location]];
 const next=checks.find(x=>!x[1]);
 const p95=values=>{const v=values.filter(x=>x!=null).sort((a,b)=>a-b);return v.length?v[Math.ceil(v.length*.95)-1]:null};
 const progress=Math.round(checks.filter(x=>x[1]).length/checks.length*100);
 const status=listening?'Listening':speaking?'Speaking':busy?'Thinking':'Ready';
 return <div className="shell">
 <aside className="sidebar"><div className="brand"><div className="brandmark"><Home size={28}/></div><div><b>Wonderly</b><small>Voice AI</small></div></div>
 <nav>{[[MessageSquare,'Conversation'],[BarChart3,'Performance']].map(([Icon,label)=><button type="button" className={'navitem '+(view===label?'active':'')} key={label} onClick={()=>setView(label)}><Icon size={20}/>{label}</button>)}</nav>
 <section className="sidequal"><h3>Lead Qualification</h3><div className="sideprogress"><span style={{width:progress+'%'}}/></div><small>{checks.filter(x=>x[1]).length} of 5 completed</small><div className="sidechecks">{checks.map(([label,value])=><div key={label}><CheckCircle2 size={19} color={value?'#4ade80':'#647b9f'}/><div><b>{label}</b><small>{value||'Awaiting answer'}</small></div></div>)}</div><div className="sidenext">{next?'Next question: '+next[0]:'All five answered — recommendation ready'}</div></section>
 <div className="sidebarfoot"><div className="kitchen">✦ Dream kitchens start here</div><p>AI-powered home remodeling sales assistant</p><small>Demo built by Shekhar Venkat</small></div></aside>
 {view==="Conversation"&&<main className="center"><section className="hero"><div className={"heroavatar "+(speaking?"avatar-talking":"")} style={{"--mouth":mouth}}><img src="/shekhar-avatar.jpg" onError={e=>{e.currentTarget.style.display='none'}} alt="Shekhar avatar"/><div className={'mini-wave '+(speaking?'live':'')}>{Array.from({length:15},(_,i)=><i key={i}/>)}</div></div><div className="herotext"><div className="eyebrow"><Sparkles size={14}/> AI SALES CONSULTANT</div><h1>Hi, I'm <span>Shekhar</span> 👋</h1><h2>Your AI remodeling consultant</h2><p>Let's plan your kitchen or bathroom renovation, explore options, and request a consultation.</p><div className="chips">{['Kitchen remodel','Bathroom remodel','Discuss budget','Schedule consultation'].map(x=><button key={x} onClick={()=>setInput(x)}>{x}</button>)}</div></div></section>
 <section className="conversation"><div className="conversationhead"><div><b>Live Conversation</b><small>Talk naturally with Shekhar AI</small></div><span className="online"><span className="dot"/> {status}</span></div>
 <div className="messages">{messages.map((m,i)=><div key={i} className={'msg '+m.role}><div className="msgavatar">{m.role==='assistant'?<img src="/shekhar-avatar.jpg" onError={e=>e.currentTarget.style.display='none'}/>:<Users size={18}/>}</div><div className="bubble">{m.content}</div></div>)}{busy&&<div className="thinking">Shekhar AI is thinking<span className="dots">...</span></div>}<div ref={bottom}/></div>
 <div className={'voicezone '+(listening||speaking?'animated':'')}><div className="wave">{Array.from({length:31},(_,i)=><i key={i} style={{'--n':i}}/>)}</div><button className={"autobutton "+(autoMode?"autoon":"")} onClick={toggleAuto}>{autoMode?"End Conversation":"Start Hands-Free Conversation"}</button><div className="voicecaption">{listening?'Listening — speak now':speaking?'Shekhar AI is speaking':busy?'Generating response...':'Start hands-free conversation to begin'}</div><small>Speak naturally after starting — no push-to-talk.</small></div>
 {error&&<div className="error">{error}</div>}
 <form className="composer" onSubmit={e=>{e.preventDefault();send()}}><input placeholder="Ask about your remodeling project..." value={input} onChange={e=>setInput(e.target.value)}/><button type="button" className="sound" onClick={()=>{setMuted(!muted);if(audio.current&&!muted){audio.current.pause();setSpeaking(false)}}}>{muted?<VolumeX size={21}/>:<Volume2 size={21}/>}</button><button type="submit" disabled={busy||!input.trim()} className="send"><Send size={21}/></button></form>
 </section></main>}
 {view==="Performance"&&<main className="center performancepage"><h1>Voice AI Performance</h1><p>Live local measurements; no simulated values.</p><div className="metricgrid"><div><small>Time to first audio</small><strong>{ttfa===null?'—':ttfa+' ms'}</strong></div><div><small>Gemma LLM</small><strong>{llm===null?'—':llm+' ms'}</strong></div><div><small>Piper synthesis</small><strong>{ttsEngine===null?'—':ttsEngine+' ms'}</strong></div><div><small>Audio request</small><strong>{tts===null?'—':tts+' ms'}</strong></div><div><small>Browser recognition*</small><strong>{stt===null?'—':stt+' ms'}</strong></div><div><small>TTFA P95</small><strong>{p95(samples.map(x=>x.ttfa))===null?'—':p95(samples.map(x=>x.ttfa))+' ms'}</strong></div></div><p className="metricnote">TTFA starts at text submission. Browser recognition timing includes listening. True VAD is not instrumented.</p></main>}
 {view==="Conversation"&&<aside className="insights"><div className="topbar"><span className="online"><span className="dot"/> Shekhar Online</span><Settings size={19}/></div>
 <div className="panel"><h3>Sales Funnel</h3><div className="funnel"><div><span>Qualification</span><b>{progress}%</b></div><div className="sideprogress light"><span style={{width:progress+'%'}}/></div><div><span>Consultation</span><b>Not booked</b></div></div><p className="metricnote">No live scheduling integration. All qualification fields are heuristically extracted; verify before use.</p></div>
 <div className="panel next"><div className="nextlabel"><CalendarDays size={20}/> NEXT BEST ACTION</div><h3>Request a Consultation</h3><p>Qualify the homeowner's project and offer a design consultation.</p><button onClick={()=>setInput('I would like to request a design consultation. What information do you need?')}><CalendarDays size={18}/> Discuss Appointment</button><small>Demo only — no live booking is performed</small></div>
 </aside>}</div>;
}
createRoot(document.getElementById('root')).render(<App/>);
