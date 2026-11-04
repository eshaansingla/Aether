import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown, ArrowUp, AudioLines, Check, CheckCircle2, Circle,
  CircleHelp, Clock3, Command, FileText, FolderSearch,  Mic,
  Moon, Music2, NotebookPen, Plus, Search, Settings2, ShieldCheck,
  Sun, Volume2, X, PanelLeftClose, PanelLeftOpen, Cpu, Paperclip,
  Square, LoaderCircle, Trash2, Save
} from "lucide-react";

const API = "http://127.0.0.1:8000";
const WAKE_PHRASES = ["hi aether","hey aether","hi ether","hey ether","hi eather","hey eather"];
type Step = {name:string;status:string;detail:string};
type Task = {task_id:string;instruction:string;status:string;message:string;steps:Step[];output_path?:string;download_url?:string;error?:string;result?:any};
type Attachment = {name:string;text:string};
type Message = {id:string;role:"user"|"assistant";content:string;task?:Task;createdAt:number;newAttachments?:string[]};
type Thread = {id:string;title:string;messages:Message[];updatedAt:number;attachments?:Attachment[]};

const starterPrompts = [
  {icon:Music2,title:"Play music",prompt:"Play some relaxing music"},
  {icon:NotebookPen,title:"Take a note",prompt:"Take a note: Ideas for my next project"},
  {icon:Clock3,title:"Set a reminder",prompt:"Remind me to take a break in 25 minutes"},
  {icon:FolderSearch,title:"Find a file",prompt:"Find my resume"},
];

function uid(){return Math.random().toString(36).slice(2)+Date.now().toString(36)}
function noteTitle(name:string){return name.replace(/\.md$/i,"").replace(/^\d{8}_\d{6}_/,"").replace(/_/g," ")}
function readThreads():Thread[]{try{return JSON.parse(localStorage.getItem("aether_threads")||"[]")}catch{return []}}
function saveThreads(t:Thread[]){localStorage.setItem("aether_threads",JSON.stringify(t.slice(0,40)))}

export default function App(){
  const [threads,setThreads]=useState<Thread[]>(readThreads);
  const [activeId,setActiveId]=useState<string|null>(null);
  const [input,setInput]=useState("");
  const [busy,setBusy]=useState(false);
  const [backend,setBackend]=useState(false);
  const [ollama,setOllama]=useState(false);
  const [modelInstalled,setModelInstalled]=useState(false);
  const [model,setModel]=useState("qwen3:4b");
  const [installedModels,setInstalledModels]=useState<string[]>([]);
  const [recording,setRecording]=useState(false);
  const [dark,setDark]=useState(true);
  const [sidebarOpen,setSidebarOpen]=useState(true);
  const [page,setPage]=useState<"chat"|"notes"|"reminders"|"settings">("chat");
  const [notes,setNotes]=useState<any[]>([]);
  const [reminders,setReminders]=useState<any[]>([]);
  const [filter,setFilter]=useState("");
  const [noteDraft,setNoteDraft]=useState<{name:string|null;title:string;content:string}|null>(null);
  const [docDraft,setDocDraft]=useState<{name:string;content:string}|null>(null);
  const [reminderDraft,setReminderDraft]=useState<{id:string|null;message:string;minutes:string;when?:string;status?:string}|null>(null);
  const [savingItem,setSavingItem]=useState(false);
  const [toast,setToast]=useState<{id:number;text:string;kind:"error"|"info"}|null>(null);
  const [confirmDraft,setConfirmDraft]=useState<{text:string;onYes:()=>void}|null>(null);
  const toastIdRef=useRef(0);
  const [pendingAttachments,setPendingAttachments]=useState<Attachment[]>([]);
  const [uploadingFile,setUploadingFile]=useState(false);
  const fileInputRef=useRef<HTMLInputElement>(null);
  const [wakeEnabled,setWakeEnabled]=useState<boolean>(()=>{try{return localStorage.getItem("aether_wake")==="1"}catch{return false}});
  const [wakeStatus,setWakeStatus]=useState<"idle"|"listening"|"capturing">("idle");
  const bottomRef=useRef<HTMLDivElement>(null);
  const mediaRef=useRef<MediaRecorder|null>(null);
  const chunksRef=useRef<Blob[]>([]);
  const recordingRef=useRef(false);
  const activeIdRef=useRef<string|null>(null);
  const wakeStreamRef=useRef<MediaStream|null>(null);
  const wakeActiveRef=useRef(false);
  const wakeBusyRef=useRef(false);
  // A plain ref, checked synchronously, so two near-simultaneous triggers (e.g. the
  // voice auto-send timer firing right as the user also presses Enter) can't both pass
  // the "not already sending" check before React state has re-rendered — `busy` state
  // alone lags a frame behind and let both calls through, filing the message twice.
  const sendingRef=useRef(false);
  const activeThread=threads.find(t=>t.id===activeId)||null;
  const messages=activeThread?.messages||[];

  // All mutations go through the functional setState form so that async callbacks
  // (fetch responses, poll ticks) always apply on top of the latest state instead of
  // a stale closure captured before the update — a stale closure here previously made
  // newly-sent messages disappear as soon as the next async patch landed.
  function updateThreads(updater:Thread[]|((prev:Thread[])=>Thread[])){
    setThreads(prev=>{
      const next = typeof updater==="function" ? (updater as (p:Thread[])=>Thread[])(prev) : updater;
      saveThreads(next);
      return next;
    });
  }
  function newChat(){
    const t:Thread={id:uid(),title:"New chat",messages:[],updatedAt:Date.now()};
    updateThreads(prev=>[t,...prev]);setActiveId(t.id);setPage("chat");setInput("");
  }
  // A toast instead of window.alert: native dialogs block the whole renderer (and were
  // freezing automated testing dead), and a quiet corner message is friendlier UX anyway.
  function notify(text:string,kind:"error"|"info"="error"){
    const id=++toastIdRef.current;
    setToast({id,text,kind});
    window.setTimeout(()=>setToast(t=>t&&t.id===id?null:t),4000);
  }
  function askConfirm(text:string,onYes:()=>void){setConfirmDraft({text,onYes})}
  function deleteThread(id:string){
    askConfirm("Delete this chat? This can't be undone.",()=>{
      updateThreads(prev=>prev.filter(t=>t.id!==id));
      if(activeIdRef.current===id){setActiveId(null);activeIdRef.current=null}
    });
  }
  function patchMessage(threadId:string,messageId:string,patch:Partial<Message>){
    updateThreads(prev=>prev.map(t=>t.id===threadId?{...t,messages:t.messages.map(m=>m.id===messageId?{...m,...patch}:m),updatedAt:Date.now()}:t));
  }
  async function refresh(){
    try{
      const [h,s,n,r]=await Promise.all([fetch(`${API}/health`),fetch(`${API}/api/status`),fetch(`${API}/api/notes`),fetch(`${API}/api/reminders`)]);
      setBackend(h.ok);
      if(s.ok){const d=await s.json();setOllama(d.ollama_online);setModelInstalled(d.model_installed);setInstalledModels(d.models||[]);setModel(d.configured_model||"qwen3:4b")}
      if(n.ok)setNotes(await n.json());if(r.ok)setReminders(await r.json());
    }catch{setBackend(false);setOllama(false)}
  }
  useEffect(()=>{refresh();const id=window.setInterval(refresh,5000);return()=>window.clearInterval(id)},[]);

  function newNote(){setNoteDraft({name:null,title:"",content:""})}
  async function openNote(name:string){
    try{
      const r=await fetch(`${API}/api/notes/${encodeURIComponent(name)}`);
      if(!r.ok)throw new Error("Could not open that note.");
      const d=await r.json();
      setNoteDraft({name:d.name,title:noteTitle(d.name),content:d.content});
    }catch(e:any){notify(e.message)}
  }
  async function saveNote(){
    if(!noteDraft||!noteDraft.content.trim())return;
    setSavingItem(true);
    try{
      if(noteDraft.name){
        const r=await fetch(`${API}/api/notes/${encodeURIComponent(noteDraft.name)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:noteDraft.content})});
        if(!r.ok)throw new Error("Could not save the note.");
      }else{
        const r=await fetch(`${API}/api/notes`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:noteDraft.title||"Untitled note",content:noteDraft.content})});
        if(!r.ok)throw new Error("Could not create the note.");
      }
      setNoteDraft(null);await refresh();
    }catch(e:any){notify(e.message)}finally{setSavingItem(false)}
  }
  function deleteNote(name:string){
    askConfirm("Delete this note? This can't be undone.",async()=>{
      setSavingItem(true);
      try{
        const r=await fetch(`${API}/api/notes/${encodeURIComponent(name)}`,{method:"DELETE"});
        if(!r.ok)throw new Error("Could not delete the note.");
        setNoteDraft(null);await refresh();
      }catch(e:any){notify(e.message)}finally{setSavingItem(false)}
    });
  }
  function newReminder(){setReminderDraft({id:null,message:"",minutes:"15"})}
  function openReminder(r:any){setReminderDraft({id:r.id,message:r.message,minutes:"",when:r.when,status:r.status})}
  async function saveReminder(){
    if(!reminderDraft||!reminderDraft.message.trim())return;
    setSavingItem(true);
    try{
      if(reminderDraft.id){
        const body:any={message:reminderDraft.message};
        if(reminderDraft.minutes.trim())body.minutes=parseInt(reminderDraft.minutes,10);
        const r=await fetch(`${API}/api/reminders/${reminderDraft.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
        if(!r.ok)throw new Error((await r.json()).detail||"Could not save the reminder.");
      }else{
        const r=await fetch(`${API}/api/reminders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:reminderDraft.message,minutes:parseInt(reminderDraft.minutes||"15",10)})});
        if(!r.ok)throw new Error((await r.json()).detail||"Could not create the reminder.");
      }
      setReminderDraft(null);await refresh();
    }catch(e:any){notify(e.message)}finally{setSavingItem(false)}
  }
  function deleteReminder(id:string){
    askConfirm("Delete this reminder?",async()=>{
      setSavingItem(true);
      try{
        const r=await fetch(`${API}/api/reminders/${id}`,{method:"DELETE"});
        if(!r.ok)throw new Error("Could not delete the reminder.");
        setReminderDraft(null);await refresh();
      }catch(e:any){notify(e.message)}finally{setSavingItem(false)}
    });
  }
  async function completeReminder(id:string){
    try{await fetch(`${API}/api/reminders/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:"done"})});await refresh()}catch{}
  }
  useEffect(()=>{bottomRef.current?.scrollIntoView({behavior:"smooth"})},[messages.length,messages[messages.length-1]?.content]);
  useEffect(()=>{document.documentElement.dataset.theme=dark?"dark":"light"},[dark]);
  useEffect(()=>{activeIdRef.current=activeId},[activeId]);

  async function uploadAttachment(file:File){
    setUploadingFile(true);
    try{
      const form=new FormData();form.append("file",file);
      const r=await fetch(`${API}/api/attachments`,{method:"POST",body:form});
      const d=await r.json();
      if(!r.ok)throw new Error(d.detail||"Could not read that file.");
      setPendingAttachments(prev=>[...prev.filter(a=>a.name!==d.name),{name:d.name,text:d.text}]);
      if(d.truncated)notify(`"${d.name}" is long, so only the first part was kept for context.`,"info");
    }catch(e:any){notify(e.message)}finally{setUploadingFile(false)}
  }
  function removePendingAttachment(name:string){setPendingAttachments(prev=>prev.filter(a=>a.name!==name))}
  function removeThreadAttachment(name:string){
    if(!activeIdRef.current)return;
    updateThreads(prev=>prev.map(t=>t.id===activeIdRef.current?{...t,attachments:(t.attachments||[]).filter(a=>a.name!==name)}:t));
  }
  async function send(text=input){
    const value=text.trim();if(!value||busy||sendingRef.current)return;
    sendingRef.current=true;
    const threadId=activeIdRef.current||uid();
    const isNewThread=!activeIdRef.current;
    const existingAttachments=threads.find(t=>t.id===threadId)?.attachments||[];
    // Newly staged files override any earlier attachment of the same name; everything
    // else already in the thread stays available so later turns can still refer to it.
    const mergedAttachments=[...existingAttachments.filter(e=>!pendingAttachments.some(p=>p.name===e.name)),...pendingAttachments];
    const userMessage:Message={id:uid(),role:"user",content:value,createdAt:Date.now(),
      newAttachments:pendingAttachments.length?pendingAttachments.map(a=>a.name):undefined};
    const assistantMessage:Message={id:uid(),role:"assistant",content:"",createdAt:Date.now()};
    // Conversational context sent to the backend so replies behave like a real chatbot
    // instead of judging every message in isolation; capped so the local model stays fast.
    const history=(threads.find(t=>t.id===threadId)?.messages||[]).filter(m=>m.content).slice(-20).map(m=>({role:m.role,content:m.content}));
    updateThreads(prev=>{
      const existing=prev.find(t=>t.id===threadId);
      const base:Thread=existing||{id:threadId,title:"New chat",messages:[],updatedAt:Date.now()};
      const title=base.messages.length?base.title:value.slice(0,34)+(value.length>34?"…":"");
      const nextThread:Thread={...base,title,messages:[...base.messages,userMessage,assistantMessage],attachments:mergedAttachments,updatedAt:Date.now()};
      return [nextThread,...prev.filter(t=>t.id!==threadId)];
    });
    if(isNewThread){setActiveId(threadId);activeIdRef.current=threadId}
    setInput("");setPage("chat");setBusy(true);setPendingAttachments([]);
    try{
      const r=await fetch(`${API}/api/tasks`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:value,history,attachments:mergedAttachments})});
      const task=await r.json();if(!r.ok)throw new Error(task.detail||"Unable to start task.");
      patchMessage(threadId,assistantMessage.id,{content:"I'm working on that.",task});
      await pollTask(threadId,assistantMessage.id,task.task_id);
    }catch(e:any){patchMessage(threadId,assistantMessage.id,{content:`I couldn't start that task: ${e.message}`});setBusy(false);sendingRef.current=false}
  }
  async function pollTask(threadId:string,messageId:string,taskId:string){
    let finished=false;
    while(!finished){
      await new Promise(resolve=>setTimeout(resolve,900));
      try{
        const r=await fetch(`${API}/api/tasks/${taskId}`);if(!r.ok)throw new Error("Task status unavailable");
        const t:Task=await r.json();
        const text=t.status==="completed"
          ? (t.result?.message || (Array.isArray(t.result)?"I found these matching files.":"Done."))
          : t.status==="failed" ? `I couldn't complete that: ${t.error||t.message}` : "I'm working on that.";
        patchMessage(threadId,messageId,{content:text,task:t});
        if(t.status==="completed"||t.status==="failed"){finished=true;setBusy(false);sendingRef.current=false;refresh()}
      }catch(e:any){patchMessage(threadId,messageId,{content:`Task status error: ${e.message}`});finished=true;setBusy(false);sendingRef.current=false}
    }
  }
  async function startRecording(){
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      const recorder=new MediaRecorder(stream);mediaRef.current=recorder;chunksRef.current=[];
      recorder.ondataavailable=e=>{if(e.data.size)chunksRef.current.push(e.data)};
      recorder.onstop=async()=>{
        setRecording(false);recordingRef.current=false;stream.getTracks().forEach(t=>t.stop());
        const blob=new Blob(chunksRef.current,{type:recorder.mimeType||"audio/webm"});
        const form=new FormData();form.append("file",blob,"aether-recording.webm");
        try{
          const r=await fetch(`${API}/api/transcribe`,{method:"POST",body:form});const d=await r.json();if(!r.ok)throw new Error(d.detail);
          // Show the recognized words for a beat before sending, so voice behaves like a
          // real voice command instead of just dictation that still needs manual Enter.
          const text=(d.text||"").trim();
          if(text){setInput(text);window.setTimeout(()=>send(text),400)}
        }
        catch(e:any){notify(`Local transcription failed: ${e.message}`)}
      };
      recorder.start();setRecording(true);recordingRef.current=true;
    }catch(e:any){notify(`Microphone unavailable: ${e.message}`)}
  }
  function stopRecording(){mediaRef.current?.stop()}
  function speak(text:string){if(!("speechSynthesis" in window)){notify("Local system speech is unavailable.");return}window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=1;window.speechSynthesis.speak(u)}
  // A plain <a download href="http://other-origin/..."> only triggers an actual download
  // in Chromium when the server sends Content-Disposition: attachment — otherwise the
  // browser just navigates there. Inside the Electron window that has no address bar or
  // back button, that navigation strands the user looking at a raw .docx with no way back
  // to the app. Fetching as a blob and downloading via a same-origin blob: URL sidesteps
  // that entirely — the window's location never changes.
  async function downloadFile(url:string,filename:string){
    try{
      const r=await fetch(url);
      if(!r.ok)throw new Error("Could not download the file.");
      const blob=await r.blob();
      const objectUrl=URL.createObjectURL(blob);
      const a=document.createElement("a");
      a.href=objectUrl;a.download=filename;
      document.body.appendChild(a);a.click();a.remove();
      URL.revokeObjectURL(objectUrl);
    }catch(e:any){notify(e.message)}
  }
  // Documents AETHER generates open for viewing/editing right here instead of only being
  // a download link — this is also what makes the Electron "stuck on a raw file" problem
  // moot for the common case: the content never leaves the SPA at all.
  async function openDocument(outputPath:string){
    const name=outputPath.split(/[\\/]/).pop()||"";
    if(!name)return;
    try{
      const r=await fetch(`${API}/api/documents/${encodeURIComponent(name)}`);
      const d=await r.json();
      if(!r.ok)throw new Error(d.detail||"Could not open that file.");
      setDocDraft({name:d.name,content:d.text});
    }catch(e:any){notify(e.message)}
  }
  async function saveDocument(){
    if(!docDraft)return;
    setSavingItem(true);
    try{
      const r=await fetch(`${API}/api/documents/${encodeURIComponent(docDraft.name)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:docDraft.content})});
      const d=await r.json();
      if(!r.ok)throw new Error(d.detail||"Could not save changes.");
      notify("Saved.","info");
    }catch(e:any){notify(e.message)}finally{setSavingItem(false)}
  }

  // Local wake-word listening: every ~3s, grabs a short clip and transcribes it with the
  // same local faster-whisper endpoint used for manual recording. If "Hi AETHER" (or a
  // close mishearing of it) shows up, the next ~5s is captured as the actual command and
  // sent automatically. Everything stays on-device, same as manual voice input — this just
  // polls faster-whisper instead of using a cloud wake-word/streaming service.
  function recordClip(ms:number,stream:MediaStream):Promise<Blob>{
    return new Promise((resolve,reject)=>{
      try{
        const recorder=new MediaRecorder(stream);const chunks:Blob[]=[];
        recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
        recorder.onstop=()=>resolve(new Blob(chunks,{type:recorder.mimeType||"audio/webm"}));
        recorder.onerror=()=>reject(new Error("Recording failed"));
        recorder.start();
        setTimeout(()=>{if(recorder.state!=="inactive")recorder.stop()},ms);
      }catch(e){reject(e)}
    });
  }
  async function transcribeBlob(blob:Blob):Promise<string>{
    const form=new FormData();form.append("file",blob,"clip.webm");
    const r=await fetch(`${API}/api/transcribe`,{method:"POST",body:form});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||"Transcription failed");
    return (d.text||"").trim();
  }
  function containsWakePhrase(text:string){
    const low=text.toLowerCase();
    return WAKE_PHRASES.some(p=>low.includes(p));
  }
  async function runWakeLoop(){
    while(wakeActiveRef.current){
      const stream=wakeStreamRef.current;
      if(!stream)break;
      if(recordingRef.current||wakeBusyRef.current){await new Promise(r=>setTimeout(r,500));continue}
      try{
        const clip=await recordClip(3000,stream);
        if(!wakeActiveRef.current)break;
        const text=await transcribeBlob(clip);
        if(text&&containsWakePhrase(text)){
          wakeBusyRef.current=true;setWakeStatus("capturing");
          const command=await recordClip(5000,stream);
          const commandText=await transcribeBlob(command);
          wakeBusyRef.current=false;
          if(wakeActiveRef.current)setWakeStatus("listening");
          if(commandText)await send(commandText);
        }
      }catch{/* a dropped clip just means try again on the next loop tick */}
      await new Promise(r=>setTimeout(r,250));
    }
  }
  async function startWakeLoop(){
    if(wakeActiveRef.current)return;
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      wakeStreamRef.current=stream;wakeActiveRef.current=true;setWakeStatus("listening");
      runWakeLoop();
    }catch(e:any){notify(`Microphone unavailable for the "Hi AETHER" activation word: ${e.message}`);setWakeEnabled(false)}
  }
  function stopWakeLoop(){
    wakeActiveRef.current=false;wakeBusyRef.current=false;
    wakeStreamRef.current?.getTracks().forEach(t=>t.stop());wakeStreamRef.current=null;
    setWakeStatus("idle");
  }
  useEffect(()=>{
    try{localStorage.setItem("aether_wake",wakeEnabled?"1":"0")}catch{}
    if(wakeEnabled)startWakeLoop();
    return()=>{stopWakeLoop()};
  },[wakeEnabled]);
  const filteredThreads=useMemo(()=>threads.filter(t=>t.title.toLowerCase().includes(filter.toLowerCase())),[threads,filter]);

  return <div className={`app ${dark?"dark":"light"}`}>
    {sidebarOpen&&<aside className="sidebar">
      <div className="side-top"><div className="brand"><span className="brand-mark">A</span><span>AETHER</span></div><button className="icon-btn subtle" onClick={()=>setSidebarOpen(false)} title="Close sidebar"><PanelLeftClose size={18}/></button></div>
      <button className="new-chat" onClick={newChat}><Plus size={17}/> <span>New chat</span><kbd>Ctrl K</kbd></button>
      <div className="side-search"><Search size={15}/><input placeholder="Search chats" value={filter} onChange={e=>setFilter(e.target.value)}/></div>
      <div className="nav-group">
        <div className="side-caption">Workspace</div>
        <button className={`nav-link ${page==="chat"?"selected":""}`} onClick={()=>setPage("chat")}><Command size={16}/> Assistant</button>
        <button className={`nav-link ${page==="notes"?"selected":""}`} onClick={()=>setPage("notes")}><NotebookPen size={16}/> Notes <span className="nav-count">{notes.length||""}</span></button>
        <button className={`nav-link ${page==="reminders"?"selected":""}`} onClick={()=>setPage("reminders")}><Clock3 size={16}/> Reminders <span className="nav-count">{reminders.length||""}</span></button>
      </div>
      <div className="history">
        <div className="side-caption">Recent</div>
        {filteredThreads.length?filteredThreads.map(t=><div className="history-row" key={t.id}><button className={`history-link ${activeId===t.id?"current":""}`} onClick={()=>{setActiveId(t.id);setPage("chat")}}><span>{t.title}</span></button><button className="history-delete" title="Delete chat" onClick={e=>{e.stopPropagation();deleteThread(t.id)}}><Trash2 size={13}/></button></div>):<div className="empty-history">Your conversations will appear here.</div>}
      </div>
      <div className="side-bottom">
        <button className={`nav-link ${page==="settings"?"selected":""}`} onClick={()=>setPage("settings")}><Settings2 size={16}/> Settings</button>
        <div className="status-line"><span className={`status-dot ${ollama?"on":""}`}/>{ollama?"Local model connected":"Waiting for Ollama"}</div>
      </div>
    </aside>}
    <main className="main">
      <header className="topbar">
        <div className="top-left">{!sidebarOpen&&<button className="icon-btn" onClick={()=>setSidebarOpen(true)}><PanelLeftOpen size={18}/></button>}<span className="top-section">{page==="chat"?"Assistant":page[0].toUpperCase()+page.slice(1)}</span></div>
        <div className="top-actions">{wakeEnabled&&<div className={`local-chip ${wakeStatus!=="idle"?"connected":""}`}><span/>{wakeStatus==="capturing"?"Listening…":"Say “Hi AETHER”"}</div>}{!backend&&<div className="local-chip warn"><span/>Backend offline</div>}<button className="icon-btn" onClick={()=>setDark(v=>!v)} title="Toggle theme">{dark?<Sun size={17}/>:<Moon size={17}/>}</button></div>
      </header>

      {page==="chat"&&<div className="chat-layout">
        <div className={`messages ${messages.length===0?"empty":""}`}>
          {messages.length===0?<div className="welcome">
            <div className="welcome-mark">A</div>
            <h1>Good to see you.</h1>
            <p>Your assistant, running privately on your computer.</p>
            <div className="prompt-list">{starterPrompts.map(({icon:Icon,title,prompt})=><button className="prompt-pill" key={title} onClick={()=>setInput(prompt)}><Icon size={15}/><span>{title}</span></button>)}</div>
            <div className="welcome-foot">Your prompts and model inference stay on this device.</div>
          </div>:<div className="conversation">{messages.map(m=><div className={`message-row ${m.role}`} key={m.id}>
            <div className="message-content">
              {m.role==="user"
                ?<>
                  {m.newAttachments&&m.newAttachments.length>0&&<div className="attach-chips end">{m.newAttachments.map(n=><span className="attach-chip" key={n}><FileText size={12}/>{n}</span>)}</div>}
                  <div className="user-bubble">{m.content}</div>
                </>
                :<>
                  <div className="message-text">{m.content||<span className="typing"><i/><i/><i/></span>}</div>
                  {m.task&&<div className="task-inline">
                    <div className="task-inline-head"><span className={`task-state ${m.task.status}`}>{m.task.status==="completed"?<CheckCircle2 size={14}/>:m.task.status==="failed"?<CircleHelp size={14}/>:<LoaderCircle size={14} className="spin"/>}{m.task.status}</span><span>{m.task.steps.filter(s=>s.status==="completed").length}/{m.task.steps.length} steps</span></div>
                    {m.task.steps.map((s,i)=><div className="task-mini-step" key={i}><span className={s.status==="completed"?"step-done":s.status==="failed"?"step-fail":"step-pending"}>{s.status==="completed"?<Check size={12}/>:s.status==="failed"?<X size={12}/>:<Circle size={10}/>}</span><span>{s.name}</span><small>{s.status}</small></div>)}
                    {m.task.output_path&&(m.task.download_url?<div className="task-file-row">
                      <button className="task-file" onClick={()=>openDocument(m.task!.output_path!)} title="Open in AETHER"><FileText size={15}/><span>{m.task.output_path}</span></button>
                      <button className="task-file-dl" onClick={()=>downloadFile(`${API}${m.task!.download_url}`,m.task!.output_path!.split(/[\\/]/).pop()||"download")} title="Download"><ArrowDown size={14}/></button>
                    </div>:<div className="task-file"><FileText size={15}/><span>{m.task.output_path}</span></div>)}
                    {Array.isArray(m.task.result)&&m.task.result.map((f:any)=><div className="task-file" key={f.path}><FileText size={15}/><span>{f.path}</span></div>)}
                  </div>}
                  {m.content&&<div className="message-tools"><button onClick={()=>navigator.clipboard?.writeText(m.content)} title="Copy response"><FileText size={14}/></button><button onClick={()=>speak(m.content)} title="Read aloud"><Volume2 size={14}/></button></div>}
                </>}
            </div>
          </div>)}<div ref={bottomRef}/></div>}
        </div>
        <div className="composer-wrap">
          {activeThread&&activeThread.attachments&&activeThread.attachments.length>0&&<div className="doc-strip">
            <span className="doc-strip-label">Documents in this chat</span>
            <div className="attach-chips">{activeThread.attachments.map(a=><span className="attach-chip" key={a.name}>{a.name}<button onClick={()=>removeThreadAttachment(a.name)} title="Remove from this chat"><X size={11}/></button></span>)}</div>
          </div>}
          <div className="composer">
          {pendingAttachments.length>0&&<div className="attach-chips pending">{pendingAttachments.map(a=><span className="attach-chip" key={a.name}><FileText size={12}/>{a.name}<button onClick={()=>removePendingAttachment(a.name)} title="Remove"><X size={11}/></button></span>)}</div>}
          <input ref={fileInputRef} type="file" hidden accept=".txt,.md,.docx,.pdf,.csv,.json,.py,.js,.ts,.html,.css,.java,.c,.cpp,.sh,.yaml,.yml,.xml,.log" onChange={e=>{const f=e.target.files?.[0];if(f)uploadAttachment(f);e.target.value=""}}/>
          <textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send()}}} placeholder="Message AETHER…" rows={1} disabled={busy}/>
          <div className="composer-bottom"><div className="composer-left"><button className="composer-tool" title="Attach a file" disabled={uploadingFile} onClick={()=>fileInputRef.current?.click()}>{uploadingFile?<LoaderCircle size={16} className="spin"/>:<Paperclip size={17}/>}</button><span className="model-label"><span className="model-pulse"/>{model}</span></div><div className="composer-right"><button className={`composer-tool ${recording?"recording":""}`} title={recording?"Stop recording":"Record voice command"} onClick={recording?stopRecording:startRecording}>{recording?<Square size={15}/>:<Mic size={17}/>}</button><button className="send-button" disabled={!input.trim()||busy||!backend} onClick={()=>send()}>{busy?<LoaderCircle size={17} className="spin"/>:<ArrowUp size={18}/>}</button></div></div>
          </div>
        <div className="composer-note">AETHER can make mistakes. Review important actions before relying on them.</div></div>
      </div>}

      {page==="notes"&&<section className="utility-page"><div className="page-heading"><div><span className="overline">Personal workspace</span><h1>Your notes</h1><p>Notes saved locally on this computer.</p></div><button className="new-item-btn" onClick={newNote}><Plus size={15}/> New note</button></div>{notes.length?notes.map(n=><article className="data-card clickable" key={n.path} onClick={()=>openNote(n.name)}><NotebookPen size={18}/><div><b>{noteTitle(n.name)}</b><small>{new Date(n.modified*1000).toLocaleString()}</small></div></article>):<div className="empty-panel"><NotebookPen size={26}/><b>No notes yet</b><p>Ask AETHER to save a note, or create one here.</p></div>}</section>}
      {page==="reminders"&&<section className="utility-page"><div className="page-heading"><div><span className="overline">Personal workspace</span><h1>Reminders</h1><p>Scheduled locally by AETHER.</p></div><button className="new-item-btn" onClick={newReminder}><Plus size={15}/> New reminder</button></div>{reminders.length?reminders.map(r=><article className={`data-card clickable ${r.status}`} key={r.id} onClick={()=>openReminder(r)}><Clock3 size={18}/><div><b>{r.message}</b><small>{new Date(r.when).toLocaleString()} · {r.status}</small></div>{r.status!=="done"&&<button className="row-action" onClick={e=>{e.stopPropagation();completeReminder(r.id)}} title="Mark done"><Check size={14}/></button>}</article>):<div className="empty-panel"><Clock3 size={26}/><b>Nothing scheduled</b><p>Try: “Remind me to stretch in 20 minutes,” or create one here.</p></div>}</section>}
      {page==="settings"&&<section className="utility-page settings-page"><div className="page-heading"><div><span className="overline">Preferences</span><h1>Settings</h1><p>Manage the local AI runtime and application.</p></div></div>
        <div className="settings-card"><div className="settings-icon"><Cpu size={20}/></div><div className="settings-body"><b>Local language model</b><p>Model inference runs through Ollama on this device. No cloud AI key is configured or required.</p><div className="settings-line"><span>Runtime</span><b className={ollama?"good":""}>{ollama?"Connected":"Not detected"}</b></div><div className="settings-line"><span>Configured model</span><b>{model}</b></div><div className="settings-line"><span>Model installed</span><b className={modelInstalled?"good":"warn"}>{modelInstalled?"Yes":"Not yet"}</b></div><div className="settings-line"><span>Installed models</span><b>{installedModels.join(", ")||"None detected"}</b></div></div></div>
        <div className="settings-card"><div className="settings-icon"><AudioLines size={20}/></div><div className="settings-body"><b>Local voice</b><p>Speech recognition uses faster-whisper locally. Read-aloud uses the operating system's available speech voices.</p><div className="settings-line"><span>Speech recognition</span><b>faster-whisper · base</b></div><div className="settings-line"><span>Text to speech</span><b>System speech engine</b></div><div className="settings-line"><span>Activation word</span><b className={wakeEnabled?"good":""}>{wakeEnabled?(wakeStatus==="capturing"?"Listening to your command…":"On · say “Hi AETHER”"):"Off"}</b></div><button className="wake-toggle" onClick={()=>setWakeEnabled(v=>!v)}><Mic size={14}/>{wakeEnabled?"Turn off “Hi AETHER”":"Turn on “Hi AETHER”"}</button><p className="settings-hint">When on, AETHER keeps a short rolling local recording and checks it for the phrase "Hi AETHER"; everything after it is sent as your command. This uses more CPU and the microphone continuously.</p></div></div>
        <div className="settings-card"><div className="settings-icon"><ShieldCheck size={20}/></div><div className="settings-body"><b>Privacy & safety</b><p>Commands are processed locally. AETHER uses an allowlist for application launching and does not expose arbitrary shell execution.</p><div className="settings-line"><span>AI API keys</span><b className="good">Not required</b></div><div className="settings-line"><span>Task database</span><b>SQLite · local</b></div></div></div>
        <div className="hardware-note"><b>Recommended hardware profile</b><span>16 GB system RAM · NVIDIA GPU with 6 GB VRAM · 256 GB free storage</span><small>Qwen3 4B Q4 is the default target. If generation is slow or memory is constrained, use qwen3:1.7b.</small></div>
      </section>}
    </main>

    {docDraft&&<div className="modal-backdrop" onClick={()=>setDocDraft(null)}><div className="modal" onClick={e=>e.stopPropagation()}>
      <div className="modal-head"><b>{docDraft.name}</b><button className="icon-btn" onClick={()=>setDocDraft(null)}><X size={18}/></button></div>
      <textarea className="modal-textarea" autoFocus value={docDraft.content} onChange={e=>setDocDraft(d=>d&&{...d,content:e.target.value})}/>
      <div className="modal-foot">
        <button className="modal-secondary" onClick={()=>downloadFile(`${API}/files/${encodeURIComponent(docDraft.name)}`,docDraft.name)}><ArrowDown size={14}/> Download</button>
        <button className="modal-primary" onClick={saveDocument} disabled={savingItem}><Save size={14}/> {savingItem?"Saving…":"Save changes"}</button>
      </div>
    </div></div>}

    {noteDraft&&<div className="modal-backdrop" onClick={()=>setNoteDraft(null)}><div className="modal" onClick={e=>e.stopPropagation()}>
      <div className="modal-head">
        {noteDraft.name?<b>{noteDraft.title}</b>:<input className="modal-title-input" autoFocus placeholder="Note title" value={noteDraft.title} onChange={e=>setNoteDraft(d=>d&&{...d,title:e.target.value})}/>}
        <button className="icon-btn" onClick={()=>setNoteDraft(null)}><X size={18}/></button>
      </div>
      <textarea className="modal-textarea" autoFocus={!!noteDraft.name} placeholder="Write your note…" value={noteDraft.content} onChange={e=>setNoteDraft(d=>d&&{...d,content:e.target.value})}/>
      <div className="modal-foot">
        {noteDraft.name&&<button className="modal-danger" onClick={()=>deleteNote(noteDraft.name!)} disabled={savingItem}><Trash2 size={14}/> Delete</button>}
        <button className="modal-primary" onClick={saveNote} disabled={savingItem||!noteDraft.content.trim()}><Save size={14}/> {savingItem?"Saving…":"Save note"}</button>
      </div>
    </div></div>}

    {reminderDraft&&<div className="modal-backdrop" onClick={()=>setReminderDraft(null)}><div className="modal modal-sm" onClick={e=>e.stopPropagation()}>
      <div className="modal-head"><b>{reminderDraft.id?"Edit reminder":"New reminder"}</b><button className="icon-btn" onClick={()=>setReminderDraft(null)}><X size={18}/></button></div>
      <div className="modal-body">
        <label className="modal-label">Message</label>
        <textarea className="modal-textarea small" placeholder="Remind me to…" value={reminderDraft.message} onChange={e=>setReminderDraft(d=>d&&{...d,message:e.target.value})}/>
        <label className="modal-label">{reminderDraft.id?"Reschedule in (minutes, optional)":"In how many minutes"}</label>
        <input className="modal-input" type="number" min={1} placeholder={reminderDraft.id?"Leave blank to keep current time":"15"} value={reminderDraft.minutes} onChange={e=>setReminderDraft(d=>d&&{...d,minutes:e.target.value})}/>
        {reminderDraft.when&&<p className="modal-hint">Currently set for {new Date(reminderDraft.when).toLocaleString()} · {reminderDraft.status}</p>}
      </div>
      <div className="modal-foot">
        {reminderDraft.id&&<button className="modal-danger" onClick={()=>deleteReminder(reminderDraft.id!)} disabled={savingItem}><Trash2 size={14}/> Delete</button>}
        <button className="modal-primary" onClick={saveReminder} disabled={savingItem||!reminderDraft.message.trim()}><Save size={14}/> {savingItem?"Saving…":"Save reminder"}</button>
      </div>
    </div></div>}

    {confirmDraft&&<div className="modal-backdrop" onClick={()=>setConfirmDraft(null)}><div className="modal modal-xs" onClick={e=>e.stopPropagation()}>
      <div className="modal-body"><p className="confirm-text">{confirmDraft.text}</p></div>
      <div className="modal-foot">
        <button className="modal-secondary" onClick={()=>setConfirmDraft(null)}>Cancel</button>
        <button className="modal-danger-solid" onClick={()=>{confirmDraft.onYes();setConfirmDraft(null)}}><Trash2 size={14}/> Delete</button>
      </div>
    </div></div>}

    {toast&&<div className={`toast ${toast.kind}`}>{toast.text}</div>}
  </div>
}
