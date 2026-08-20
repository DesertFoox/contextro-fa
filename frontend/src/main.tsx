import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Flame, Snowflake, Trophy} from 'lucide-react';
import './styles.css';

type Guess = {word:string; proximity:number; cosine_similarity:number; rank:number|null; temperature:string; is_correct:boolean; message:string};
const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const sid = localStorage.getItem('contextro_sid') ?? crypto.randomUUID();
localStorage.setItem('contextro_sid', sid);

function App(){
  const [word,setWord]=useState(''); const [history,setHistory]=useState<Guess[]>([]); const [busy,setBusy]=useState(false); const [msg,setMsg]=useState('');
  const best=useMemo(()=>Math.max(0,...history.map(x=>x.proximity)),[history]);
  async function load(){const r=await fetch(`${API}/api/status`,{headers:{'X-Session-Id':sid}}); if(r.ok){const j=await r.json();setHistory(j.history)}}
  useEffect(()=>{load()},[]);
  async function guess(e:React.FormEvent){e.preventDefault(); if(!word.trim()||busy)return; setBusy(true); const r=await fetch(`${API}/api/guess`,{method:'POST',headers:{'Content-Type':'application/json','X-Session-Id':sid},body:JSON.stringify({word})}); const j=await r.json(); setMsg(j.message); setWord(''); await load(); setBusy(false)}
  return <main className="page"><section className="hero"><span className="badge">پروژه NLP فارسی</span><h1>Contextro <b>FA</b></h1><p>کلمه مخفی امروز را با نزدیک‌شدن معنایی پیدا کن.</p><div className="stats"><span>تلاش <b>{history.length}</b></span><span>بهترین <b>{best.toFixed(1)}</b></span></div></section>
  <form onSubmit={guess} className="guessBox"><input value={word} onChange={e=>setWord(e.target.value)} placeholder="یک کلمه فارسی حدس بزن…" autoFocus/><button disabled={busy}>حدس بزن</button></form>
  {msg && <div className="message">{msg}</div>}
  <section className="legend"><span><Snowflake size={16}/> دور</span><span><Flame size={16}/> نزدیک</span><span><Trophy size={16}/> جواب</span></section>
  <section className="list">{history.map((g,i)=><article key={`${g.word}-${i}`} className={`row ${g.temperature}`}><div className="rank">#{g.rank ?? '—'}</div><div className="word">{g.word}<small>{g.temperature}</small></div><div className="bar"><i style={{width:`${g.proximity}%`}}/></div><strong>{g.proximity.toFixed(1)}</strong></article>)}</section>
  <footer>Similarity با embedding محاسبه می‌شود؛ امتیاز نمایش‌داده‌شده probability نیست.</footer></main>
}
createRoot(document.getElementById('root')!).render(<App/>);
