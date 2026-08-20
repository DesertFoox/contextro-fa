const sid = localStorage.getItem('contextro_sid') || crypto.randomUUID();
localStorage.setItem('contextro_sid', sid);
let latestStatus = null;

const $ = (id) => document.getElementById(id);
const form = $('guess-form'), input = $('word-input'), button = $('guess-button'), message = $('message');
const historyEl = $('history'), countEl = $('guess-count'), bestEl = $('best-score'), roundEl = $('round-count');
const hintButton = $('hint-button'), hintEl = $('hint'), hintCountEl = $('hint-count'), nextButton = $('next-button');
const giveupButton = $('giveup-button'), shareButton = $('share-button'), labButton = $('lab-button');
const totalScoreEl = $('total-score'), streakEl = $('streak-count');
const journeyCard = $('journey-card'), journeyEl = $('journey'), neighborsCard = $('neighbors-card'), neighborsEl = $('neighbors');
const labPanel = $('lab-panel'), labContent = $('lab-content');

function escapeHtml(value='') { return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch])); }
function heatEmoji(score){ if(score>=100)return '🏆'; if(score>=88)return '🚨'; if(score>=70)return '🔥'; if(score>=45)return '🙂'; if(score>=22)return '❄️'; return '🥶'; }

function render(history) {
  countEl.textContent = history.length;
  const best = history.reduce((max, item) => Math.max(max, item.proximity), 0);
  bestEl.textContent = best.toFixed(1);
  historyEl.innerHTML = [...history].map((g) => `
    <article class="row ${escapeHtml(g.temperature)}">
      <div class="rank">#${g.rank ?? '—'}</div>
      <div class="word">${escapeHtml(g.word)}<small>${heatEmoji(g.proximity)} ${escapeHtml(g.temperature)}</small></div>
      <div class="bar"><i style="width:${Math.min(100, Math.max(0, g.proximity))}%"></i></div>
      <strong>${Number(g.proximity).toFixed(1)}</strong>
    </article>`).join('');
  renderJourney(history);
}

function renderJourney(history){
  if(!history.length){ journeyCard.classList.add('hidden'); return; }
  journeyCard.classList.remove('hidden');
  const ordered=[...history].slice().reverse().slice(-12);
  journeyEl.innerHTML = ordered.map((g,i)=>{
    const d = Math.max(5, 100 - Number(g.proximity));
    const angle = (i/Math.max(1, ordered.length))*Math.PI*2;
    const x=50+Math.cos(angle)*d*.42, y=50+Math.sin(angle)*d*.42;
    return `<div class="journeyDot" title="${escapeHtml(g.word)} • #${g.rank}" style="left:${x}%;top:${y}%;transform:translate(-50%,-50%) scale(${.75+g.proximity/250})"><span>${escapeHtml(g.word)}</span></div>`;
  }).join('') + '<div class="targetDot">هدف</div>';
}

function renderNeighbors(items){
  if(!items?.length){ neighborsCard.classList.add('hidden'); return; }
  neighborsCard.classList.remove('hidden');
  neighborsEl.innerHTML=items.map(x=>`<div class="neighbor"><b>#${x.rank}</b><span>${escapeHtml(x.word)}</span><small>${Number(x.proximity).toFixed(1)}</small></div>`).join('');
}

async function loadStatus() {
  const response = await fetch('/api/status', {headers: {'X-Session-Id': sid}});
  if (!response.ok) throw new Error('خطا در دریافت وضعیت بازی');
  const data = await response.json(); latestStatus = data;
  render(data.history || []); renderNeighbors(data.top_neighbors || []);
  const remaining = Math.max(0, Number(data.max_hints || 3) - Number(data.hints_used || 0));
  hintCountEl.textContent = remaining; roundEl.textContent = Number(data.round || 1);
  totalScoreEl.textContent = Number(data.score || 0); streakEl.textContent = Number(data.streak || 0);
  const ended = Boolean(data.solved || data.gave_up);
  hintButton.disabled = remaining <= 0 || ended; giveupButton.disabled = ended;
  nextButton.classList.toggle('hidden', !Boolean(data.can_next)); input.disabled = ended; button.disabled = ended;
  if (ended && data.target_reveal) {
    message.textContent = data.gave_up ? `🏳️ جواب «${data.target_reveal}» بود.` : `🏆 جواب «${data.target_reveal}» بود. آماده‌ای بری کلمه بعدی؟`;
    message.classList.remove('hidden');
  }
}

nextButton.addEventListener('click', async () => {
  nextButton.disabled = true;
  try { const r=await fetch('/api/next',{method:'POST',headers:{'X-Session-Id':sid}}); const d=await r.json(); if(!r.ok)throw new Error(d.detail||'خطا'); hintEl.classList.add('hidden'); message.classList.add('hidden'); neighborsCard.classList.add('hidden'); input.disabled=false; button.disabled=false; input.value=''; await loadStatus(); input.focus(); }
  catch(e){ message.textContent=e.message; message.classList.remove('hidden'); } finally{ nextButton.disabled=false; }
});

hintButton.addEventListener('click', async () => {
  if(hintButton.disabled)return; hintButton.disabled=true;
  try { const r=await fetch('/api/hint',{method:'POST',headers:{'X-Session-Id':sid}}); const d=await r.json(); if(!r.ok)throw new Error(d.detail||'خطا'); hintEl.innerHTML=`<b>راهنمایی ${d.level}</b><span>${escapeHtml(d.hint)}</span>${d.category?`<small>دسته: ${escapeHtml(d.category)}</small>`:''}`; hintEl.classList.remove('hidden'); hintCountEl.textContent=d.remaining; }
  catch(e){ message.textContent=e.message; message.classList.remove('hidden'); } finally{ if(Number(hintCountEl.textContent)>0)hintButton.disabled=false; }
});

giveupButton.addEventListener('click', async()=>{
  if(!confirm('مطمئنی می‌خوای جواب این راند رو ببینی؟ استریک صفر می‌شه.'))return;
  const r=await fetch('/api/give-up',{method:'POST',headers:{'X-Session-Id':sid}}); const d=await r.json();
  if(!r.ok){ message.textContent=d.detail||'خطا'; message.classList.remove('hidden'); return; }
  await loadStatus();
});

shareButton.addEventListener('click', async()=>{
  if(!latestStatus)return;
  const rows=(latestStatus.history||[]).slice(0,8).map(x=>`${heatEmoji(x.proximity)} ${x.word} #${x.rank}`).join('\n');
  const result=`Contextro FA • راند ${latestStatus.round}\n${latestStatus.solved?'🏆 حل شد':'🧠 در حال بازی'} • ${latestStatus.guesses} تلاش • امتیاز ${latestStatus.score}\n${rows}`;
  try{ await navigator.clipboard.writeText(result); message.textContent='📋 نتیجه کپی شد.'; }
  catch{ message.textContent=result; }
  message.classList.remove('hidden');
});

labButton.addEventListener('click', async()=>{
  labPanel.classList.remove('hidden'); labContent.innerHTML='<span>در حال خواندن معیارها…</span>';
  const r=await fetch('/api/lab'); const d=await r.json();
  const bench=d.benchmark||{};
  labContent.innerHTML=`
    <div><b>${d.vocabulary.toLocaleString('fa-IR')}</b><span>واژه در فضای رتبه‌بندی</span></div>
    <div><b>${d.targets.toLocaleString('fa-IR')}</b><span>کلمه هدف</span></div>
    <div><b>${d.relations.toLocaleString('fa-IR')}</b><span>رابطه وزن‌دار</span></div>
    <div><b>${d.categories.toLocaleString('fa-IR')}</b><span>حوزه معنایی</span></div>
    <div class="wide"><b>${bench.pairwise_order_accuracy!=null ? (Number(bench.pairwise_order_accuracy)*100).toFixed(1)+'٪' : escapeHtml(bench.summary || bench.note || 'فعال')}</b><span>Pairwise semantic ordering در benchmark داخلی (${bench.cases || '—'} سناریو)</span></div>`;
  labPanel.scrollIntoView({behavior:'smooth'});
});
$('close-lab').addEventListener('click',()=>labPanel.classList.add('hidden'));

form.addEventListener('submit', async (event) => {
  event.preventDefault(); const word=input.value.trim(); if(!word||button.disabled)return;
  button.disabled=true; button.textContent='در حال بررسی…';
  try { const r=await fetch('/api/guess',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Id':sid},body:JSON.stringify({word})}); const d=await r.json(); if(!r.ok)throw new Error(d.detail||'خطا'); message.textContent=d.is_correct&&d.round_score?`${d.message} +${d.round_score} امتیاز` : d.message; message.classList.remove('hidden'); input.value=''; await loadStatus(); }
  catch(e){ message.textContent=e.message||'خطای ناشناخته'; message.classList.remove('hidden'); }
  finally{ button.disabled=Boolean(latestStatus?.solved||latestStatus?.gave_up); button.textContent='حدس بزن'; input.focus(); }
});

loadStatus().catch(e=>{ message.textContent=e.message; message.classList.remove('hidden'); });
