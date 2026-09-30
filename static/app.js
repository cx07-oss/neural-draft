'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s = '') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clean = (s = '') => esc(String(s).replaceAll(';', '.').replace(/\s+/g, ' ').trim());
const NAME_ALIASES = {'Signal Warden':'Cross-Check','Trace Vector':'Trace','Sourcekeeper':'Source Check','Audit Sentinel':'Verify','Parallax':'Second Source','Firewall':'Lockdown','Stabiliser':'Stabilise','Safehold':'Safe Hold','Barrier':'Shield','Containment Node':'Damage Control','Counterpoint':'Counterclaim','Contradiction':'Reality Check','Fault Line':'Pressure Test','Command Link':'Team Link','Rally Point':'Rally','Ghost Protocol':'Cross-Check','Zero-Hour Diplomat':'Dual Channel','Continuity Shield':'Stabilise','Signal Cartographer':'Source Check','Quiet Firewall':'Safe Hold','Assumption Breaker':'Reality Check','Relay Architect':'Team Link','Trace Lens':'Trace','Circuit Shelter':'Shield','Human Relay':'Relay'};
function cardName(card) { let name=String(card.name||card.archetype||'Card'); for(const [oldName,newName] of Object.entries(NAME_ALIASES)) name=name.replace(oldName,newName); return clean(name); }
const params = new URLSearchParams(location.search);
const slot = params.get('pilot') === 'B' ? 'B' : params.get('pilot') === 'A' ? 'A' : 'default';
const key = `neural-draft-${slot}`;
const state = {token: localStorage.getItem(key) || '', profile: null, config: null, route: 'home', selectedCard: '',
  attempt: null, openEvidence: new Set(), domain: 'random', battleText: '', reason: '', question: '', busy: false,
  room: null, socket: null, connected: false, reconnect: null, ping: null,
  playCard: '', front: '', lastRound: '', card: null, notice: ''};
let toastTimer;
function toast(message, error = false) { const t = $('#toast'); t.textContent = String(message).replaceAll(';', '.'); t.className = `toast ${error ? 'error' : ''}`; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, error ? 7500 : 4000); }
async function api(path, body) {
  const response = await fetch(`/api${path}`, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json','X-Player': state.token}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  let data; try {data = await response.json();} catch {throw new Error('The server could not respond. Please try again.');}
  if (!response.ok) {const error=new Error(typeof data.detail === 'string' ? data.detail : 'Check your input and try again.');error.status=response.status;throw error;}
  return data;
}
function nav(route) { if (location.hash === `#${route}`) routeChanged(); else location.hash = route; }
function art(kind, seed = '', evolution = '') {
  const n = [...seed].reduce((sum, c) => sum + c.charCodeAt(0), 0);
  const offset = n % 18;
  const scenes = {
    Investigate: `<g class="art-scene"><path d="M34 45h82v82H34z" fill="currentColor" fill-opacity=".045"/><path d="M48 58h54M48 70h38M48 94h54M48 106h30"/><path d="M130 47h86v68h-86z" fill="currentColor" fill-opacity=".07"/><path d="M143 62h56M143 76h42M143 90h50"/><circle cx="130" cy="98" r="31" fill="#080D14" fill-opacity=".72"/><circle cx="130" cy="98" r="25"/><path d="m149 118 24 22M116 98h28m-14-14v28"/><path d="M102 70 130 58l28 18" stroke-dasharray="3 5"/></g>`,
    Contain: `<g class="art-scene"><path d="M38 44h204v94H38z" fill="currentColor" fill-opacity=".035"/><path d="M55 58v66m170-66v66M70 69h34v44H70zm106 0h34v44h-34z"/><path d="m140 40 39 17v35q0 27-39 50-39-23-39-50V57z" fill="#080D14" fill-opacity=".76"/><path d="m140 52 28 12v27q0 19-28 38-28-19-28-38V64z" fill="currentColor" fill-opacity=".10"/><path d="m126 90 10 10 20-27" stroke-width="2"/><path d="M55 48h170M55 134h170" stroke-dasharray="4 6"/></g>`,
    Challenge: `<g class="art-scene"><path d="M30 52h82v76H30zM168 52h82v76h-82z" fill="currentColor" fill-opacity=".035"/><path d="M40 92h12l8-17 10 34 10-24 9 7h13M178 92h11l8 11 10-40 10 29h23"/><path d="M112 91h56" stroke-dasharray="4 5"/><path d="m141 35-14 43 19 10-18 47 35-57-18-9 13-34z" fill="currentColor" fill-opacity=".28"/><circle cx="140" cy="88" r="43" stroke-dasharray="2 7"/><path d="M86 58l16 16m92 38 16 16" stroke-width="2"/></g>`,
    Coordinate: `<g class="art-scene"><path d="M42 112 92 60l48 31 52-47 46 66"/><path d="M42 112h196" stroke-dasharray="3 6"/><path d="M92 60 140 132l52-88M42 112l98-21 98 19" opacity=".55"/><circle cx="42" cy="112" r="12"/><circle cx="92" cy="60" r="14"/><circle cx="140" cy="91" r="19" fill="currentColor" fill-opacity=".11"/><circle cx="192" cy="44" r="14"/><circle cx="238" cy="110" r="12"/><path d="m132 91 7 7 13-16" stroke-width="2"/><path d="M140 30v26m0 71v19" stroke-dasharray="3 5"/></g>`
  };
  const aura = evolution === 'Luminous' ? '<path d="M18 30h20M18 30v20m244-20h-20m20 0v20M18 140h20m-20 0v-20m244 20h-20m20 0v-20" class="art-aura"/>' : evolution === 'Focused' ? '<rect x="17" y="18" width="246" height="134" rx="9" class="art-aura" stroke-dasharray="28 10"/>' : '';
  return `<svg class="card-art" viewBox="0 0 280 170" fill="none" aria-hidden="true"><g stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="10" y="10" width="260" height="150" rx="10" class="art-frame"/><path d="M22 ${32+offset}h20m196 ${92-offset}h20M${58+offset} 18v12M${218-offset} 140v12" class="art-grid"/>${aura}${scenes[kind] || scenes.Investigate}</g></svg>`;
}
function abilityCopy(card) {
  return clean(String(card.effect || '').replace(/Success:/gi, 'Ability:').replace(/Partial:/gi, 'Partial:'));
}
function cardHTML(card, opts = {}) {
  const tag = opts.click ? 'button' : 'article';
  const collection = !!opts.collection;
  const hand = opts.click === 'play-card';
  return `<${tag} class="skill-card rarity-${esc(card.rarity||'COMMON')} ${esc(card.archetype)} ${opts.selected ? 'selected' : ''} ${collection?'collection-card':''} ${hand?'hand-card':''}" ${opts.click ? `data-action="${opts.click}" data-id="${esc(card.id)}" aria-pressed="${!!opts.selected}" aria-label="${cardName(card)}, ${esc(card.archetype)}"` : ''} ${opts.disabled ? 'disabled' : ''}>
    <div class="card-top"><span>${esc(card.archetype.toUpperCase())}</span><span class="rarity-label">${card.demo?`PRACTICE · ${esc(card.rarity||'COMMON')}`:card.evolution==='Starter'?'STARTER':esc(card.rarity||'COMMON')}</span></div>
    ${art(card.archetype, card.id, card.evolution)}<h3>${cardName(card)}</h3>
    ${collection?'':`<div class="card-skill">${clean(card.skill)}</div><div class="ability-title">${clean(card.ability_name||card.archetype)}</div><p class="card-effect">${abilityCopy(card)}</p><p class="card-flavour">“${clean(card.flavour)}”</p><div class="card-bottom"><span>${clean(card.evolution)}</span><span>${card.demo ? 'PRACTICE' : card.evolution === 'Starter' ? 'CORE / 05' : 'FORGED'}</span></div>`}${opts.used ? '<div class="used-label">USED</div>' : ''}</${tag}>`;
}
const sample = {id:'landing',name:'Cross-Check',archetype:'Investigate',skill:'Independent verification',effect:'Base +2. Ability: +1 here and +1 on your weakest front.',ability_name:'Cross-Reference',rarity:'RARE',flavour:'Compare the signals. Make the call.',evolution:'Luminous'};
function homeHTML() {
  return `<section class="hero"><div class="hero-copy"><div class="eyebrow">Forge your next move</div><h1>Your judgement.<br>Your card.<br><span>Your advantage.</span></h1><p class="intro">Turn a real decision into a card, then play it in a tactical duel.</p><div class="button-row"><button class="btn primary" data-go="forge">Forge a card</button><a class="btn secondary" href="/demo?pilot=A">Quick duel</a></div></div><div class="hero-art"><svg class="constellation" viewBox="0 0 500 500" fill="none" aria-hidden="true"><g stroke="#527587" stroke-width=".6"><path d="m40 70 160 30 110-70 130 110-30 220-170 95L50 310zM40 70l200 385m-190-145L440 140M200 100l210 260M50 310l150-210 40 355"/><circle cx="250" cy="250" r="202" stroke-dasharray="2 10"/></g><g fill="#42C6E8"><circle cx="40" cy="70" r="3"/><circle cx="440" cy="140" r="3"/><circle cx="410" cy="360" r="3"/><circle cx="50" cy="310" r="3"/><circle cx="240" cy="455" r="3"/></g></svg><div class="ghost-card"></div>${cardHTML(sample)}<div class="hero-tag">Earned through action</div></div></section>
  <section class="step-strip" aria-label="How it works"><div class="step"><div><h3>Read the case</h3><p>Inspect the evidence.</p></div></div><div class="step"><div><h3>Make the call</h3><p>Forge your card.</p></div></div><div class="step"><div><h3>Enter battle</h3><p>Four rounds. Three fronts.</p></div></div></section>
  <div class="quick-bar demo-links"><div class="button-row"><a class="btn small secondary" href="/demo?pilot=A">Demo seat A</a><a class="btn small secondary" href="/demo?pilot=B" target="_blank" rel="noopener">Demo seat B</a></div></div>`;
}
function identityHTML() {
  return `<section class="panel form-panel"><div class="eyebrow">New profile</div><h1>Choose a nickname</h1><p>It will appear on your cards and at the battle table.</p><form id="identity-form"><div class="form-field"><label for="nickname">Nickname</label><input id="nickname" name="nickname" required minlength="1" maxlength="18" autocomplete="nickname" placeholder="Nova"></div><button class="btn primary wide" ${state.busy?'disabled':''}>${state.busy?'Preparing…':'Start forging'}</button></form></section>`;
}
function rubricHTML() {
  return `<details class="rubric"><summary>Assessment rubric</summary>${state.config.rubric.map(r=>`<div class="rubric-row"><strong>${clean(r.title)}</strong><ul>${r.levels.map(l=>`<li>${clean(l)}</li>`).join('')}</ul></div>`).join('')}<p class="small-copy muted">Each skill scores 0–2. Scores shape the card’s theme.</p></details>`;
}
function forgeHTML() {
  if (!state.profile) return identityHTML();
  if (!state.attempt) return '<div class="loading">Opening case…</div>';
  const a=state.attempt,c=a.scenario,q=a.questions?.at(-1),review=a.assessment;
  return `<div class="breadcrumb"><span class="current">01 Case</span><span>02 Card</span><span>03 Battle</span></div>
  <div class="case-switch"><label for="case-domain">Case world</label><select id="case-domain"><option value="random">Surprise me</option>${state.config.domains.map(d=>`<option value="${d}" ${state.domain===d?'selected':''}>${clean(d)}</option>`).join('')}</select><button class="btn small secondary" data-action="new-case" ${state.busy?'disabled':''}>New case</button>${state.config.ai_status?.scenario_available?`<button class="text-btn" data-action="generate-case" ${state.busy?'disabled':''}>Generate case</button>`:''}<button class="text-btn" data-action="demo-case" ${state.busy?'disabled':''}>Demo case</button></div>
  <div class="section-head case-heading"><div class="page-intro"><div class="eyebrow">${clean(c.domain)}</div><h1>${clean(c.title)}</h1><p>${clean(c.brief)}</p></div><span class="pill amber">${clean(c.difficulty)}</span></div>
  <div class="incident-pressure"><span>◷ ${clean(c.time_pressure)}</span><p>${clean(c.stakes)}</p></div>
  <div class="forge-grid"><section><div class="section-head"><h2>Evidence</h2><span class="tag">${a.evidence.length} / ${c.evidence.length} viewed</span></div><div class="evidence-list">${c.evidence.map(e=>{const open=state.openEvidence.has(e.id),seen=a.evidence.includes(e.id);return `<article class="evidence ${open?'open':''}"><button class="inspect" data-action="inspect" data-id="${esc(e.id)}" aria-expanded="${open}" ${state.busy?'disabled':''}><span class="evidence-number">${clean(e.id)}</span><h3>${clean(e.title)}</h3><span class="read-label">${seen?'Viewed':'View'}</span></button>${open?`<div class="evidence-body"><p>${clean(e.text)}</p><details><summary>What does this mean?</summary><p>${clean(e.reliability)} confidence. Reliable evidence can still leave the cause uncertain.</p></details></div>`:''}</article>`;}).join('')}</div></section>
  <aside class="character-panel"><div class="character-head"><span class="avatar">${esc(c.characters[0].name.split(' ').map(n=>n[0]).join(''))}</span><div><h3>${clean(c.characters[0].name)}</h3><p>${clean(c.characters[0].role)}</p></div></div><div class="chat">${q?`<p class="asked">You: ${clean(q.question)}</p><p>${clean(q.answer)}</p>`:`<p>“${clean(c.characters[0].initial_message)}”</p>`}</div><form id="ask-form" class="chat-form"><label class="hidden" for="question">Ask a question</label><input id="question" placeholder="Ask about the case…" maxlength="240" minlength="2" required value="${esc(state.question)}"><button class="btn small secondary" aria-label="Ask question" ${state.busy?'disabled':''}>Ask</button></form>${c.characters.slice(1).map(x=>`<hr class="divider"><strong>${clean(x.name)}</strong><p class="small-copy">${clean(x.role)}</p><p>${clean(x.initial_message)}</p>`).join('')}${rubricHTML()}</aside></div>
  ${review?.verdict==='fail'?`<section class="unstable" role="status"><div class="eyebrow">Try again</div><h2>Make the decision more specific</h2><p>${clean(review.feedback)}</p><p class="small-copy">${a.can_retry?'Name a case detail and the risk your action addresses.':'Start a new case to try another decision.'}</p></section>`:''}
  <section class="decision-panel"><div class="eyebrow">Your decision</div><h2>What would you do?</h2><form id="forge-form"><label class="hidden" for="reason">Your decision</label><textarea id="reason" maxlength="1200" rows="4" placeholder="I would… because…" ${state.busy||!a.can_retry?'disabled':''}>${esc(state.reason)}</textarea>${state.busy?`<div class="forge-progress" role="status"><strong>Analysing decision</strong><span>Evidence</span><span>Risk</span><span>Approach</span></div>`:''}<div class="decision-footer"><span class="small-copy muted">One action. One reason.</span><button id="forge-submit" class="btn primary" ${state.busy||!a.can_retry?'disabled':''}>${state.busy?'Analysing…':review?'Analyse again':'Analyse and forge'}</button></div></form></section>`;
}
function provenanceHTML(card) {
  const p=card.provenance, review=card.assessment;
  if (!p) return '';
  const rounds=state.room?.history?.filter(h=>h.plays?.[state.room.seat]?.card?.id===card.id).length||0;
  const matchRecord=rounds?`${rounds} ${rounds===1?'round':'rounds'} played this session`:'No rounds played this session';
  if(p.version===3) {
    const labels={verification:'Independent verification',evidence:'Evidence use',risk:'Risk awareness',tradeoff:'Risk awareness',reversible:'Reversible action',containment:'Proportionate response',coordination:'Coordination',challenge:'Constructive challenge'};
    const signals=[...new Set((review.signals||[]).map(s=>labels[s.signal]||String(s.signal||'').replaceAll('_',' ')))].filter(Boolean).slice(0,3);
    return `<div class="reasoning-detected"><span class="tag">Reasoning detected</span>${(signals.length?signals:[review.demonstrated_skill]).map(s=>`<span>✓ ${clean(s)}</span>`).join('')}</div><dl class="provenance"><dt>Origin</dt><dd>${clean(card.source_scenario)} · ${clean(card.domain)}</dd><dt>Your decision</dt><dd>“${clean(p.reason)}”</dd><dt>Evidence</dt><dd>${review.evidence_ids.map(id=>clean(p.evidence_snapshot.find(e=>e.id===id)?.title||id)).join(' · ')||'No evidence cited'}</dd><dt>Match record</dt><dd>${matchRecord}</dd></dl>`;
  }
  const legacyActions={verify:'Pause. Verify. Preserve.',isolate:'Isolate the test laptops',install:'Trust the urgent update'};
  const legacyEvidence={request:'An urgent favour',signature:'A signature out of place',scope:'The blast radius'};
  const actionTitle=p.action_title||legacyActions[p.action]||p.action;
  const evidenceTitles=p.evidence_titles||p.inspected.map(id=>legacyEvidence[id]||id);
  return `${review.mode!=='demo'?`<div class="score-grid">${state.config.rubric.map(r=>`<div class="score-box"><strong>${review.scores[r.key]}<span> / 2</span></strong><span>${clean(r.title)}</span></div>`).join('')}</div><dl class="provenance"><dt>Action</dt><dd>${clean(actionTitle)}${p.focus?` · ${p.focus==='claim'?'Test approval claim':'Verify source'}`:''}</dd><dt>Evidence</dt><dd>${evidenceTitles.length?evidenceTitles.map(clean).join(' · '):'No evidence viewed'}</dd><dt>Your decision</dt><dd>“${clean(p.reason)}”</dd><dt>Match record</dt><dd>${matchRecord}</dd></dl>`:''}`;
}
function skillLink(card) {
  return `${card.prompt||state.config.abilities[card.ability_id]?.prompt||'Apply the same skill in the next case.'}`;
}
function forgedBecause(card) {
  const reasons={Investigate:'you verified the source before committing',Contain:'you reduced the immediate risk before proceeding',Challenge:'you tested a claim instead of accepting it',Coordinate:'you aligned people before acting'};
  return card.demo?'Practice card. No decision assessed.':`Forged because ${reasons[card.archetype]||'your decision showed sound judgement'}.`;
}
function earnedHTML(card) {
  return `${card.demo?'':'<span class="tag">Forged because</span>'}<p class="earned-record">${clean(forgedBecause(card))}</p>`;
}
function frameworkHTML(cards=[]) {
  const earned=cards.filter(c=>!c.demo);
  const found=new Set(earned.flatMap(c=>[c.archetype.toLowerCase(),c.pattern]).filter(id=>state.config.patterns.some(p=>p.id===id)));
  return `<section class="decision-profile"><div class="section-head"><h2>Decision profile</h2><span class="tag">${earned.length} forged</span></div><div class="profile-counts">${['Investigate','Contain','Challenge','Coordinate'].map(kind=>`<div><strong>${earned.filter(c=>c.archetype===kind).length}</strong><span>${kind}</span></div>`).join('')}</div><details class="patterns"><summary>Patterns · ${found.size} discovered</summary><div class="pattern-grid">${state.config.patterns.map(p=>`<div class="pattern ${found.has(p.id)?'discovered':''}"><strong>${found.has(p.id)?'✓':'◇'} ${clean(p.label)}</strong><span>${clean(p.kind)}</span></div>`).join('')}</div></details></section>`;
}
function revealHTML() {
  const card=state.card; if (!card) return '<div class="loading">Loading card…</div>';
  return `<div class="breadcrumb"><span>01 Case</span><span class="current">02 Card</span><span>03 Battle</span></div><section class="reveal-layout"><div><div class="reveal-stage">${cardHTML(card)}</div></div><div class="reveal-copy"><div class="eyebrow">${card.demo?'Practice card':'Card forged'}</div><h1>${cardName(card)}</h1>${earnedHTML(card)}<div class="reveal-ability"><span class="tag">Ability</span><strong>${clean(card.ability_name)}</strong><p>${abilityCopy(card)}</p></div>${provenanceHTML(card)}<div class="skill-link"><span class="tag">Use it in battle</span><p>${clean(skillLink(card))}</p></div><div class="button-row"><button class="btn primary" data-go="collection">Play card</button><button class="text-btn" data-go="forge">New case</button></div></div></section>`;
}
function collectionHTML() {
  if(!state.profile) return identityHTML();
  const cards=state.profile.cards;
  if(!cards.length) return `<section class="empty"><div class="eyebrow">Collection</div><h1>Forge your first card</h1><button class="btn primary" data-go="forge">New case</button></section>`;
  if(!cards.some(c=>c.id===state.selectedCard)) state.selectedCard=cards[0].id;
  return `<div class="section-head collection-heading"><div><div class="eyebrow">Collection</div><h1>Your cards</h1><p class="small-copy">${cards.length} ${cards.length===1?'card':'cards'}</p></div><button class="btn small secondary" data-go="forge">New case</button></div><div class="collection-layout"><section><div class="collection-cards">${cards.map(c=>`<div class="collection-item">${cardHTML(c,{click:'select-card',selected:c.id===state.selectedCard,collection:true})}<button class="text-btn" data-action="view-card" data-id="${c.id}">View card</button></div>`).join('')}</div></section><aside class="play-panel"><div class="eyebrow">Battle</div><h2>Choose your rival</h2><div class="pill cyan">2 players · 3 fronts · 4 rounds</div><button class="btn primary wide" data-action="create-room" ${state.busy?'disabled':''}>Create room</button><div class="or-rule"><span>or</span></div><form id="join-form" class="join-form"><label class="hidden" for="room-code">Room code</label><input id="room-code" placeholder="Room code" maxlength="5" minlength="5" required autocomplete="off" aria-label="Room code"><button class="btn secondary small" ${state.busy?'disabled':''}>Join room</button></form>${sessionStorage.getItem(`${key}-room`)?'<button class="text-btn resume-room" data-action="resume-room">Return to room</button>':''}</aside></div>${frameworkHTML(cards)}`;
}
function connectionHTML() {return `<span class="connection ${state.connected?'':'offline'}">● ${state.connected?'Live':'Reconnecting…'}</span>`;}
function lobbyHTML() {
  const r=state.room;
  return `<section class="lobby"><div class="eyebrow">Battle lobby</div><h1>Waiting for a rival</h1><div class="lobby-code"><span class="tag">Room code</span><div class="room-code">${r.code}</div><button class="btn small secondary" data-action="copy-code">Copy code</button></div><div class="lobby-slots"><div class="lobby-slot ready"><i class="status-dot"></i><strong>${clean(r.names[0])}</strong><p>Seat A · Ready</p></div><div class="lobby-slot"><span class="muted pulse">Waiting…</span><p>Seat B · Open</p></div></div><a class="btn secondary" href="/demo?pilot=B&room=${r.code}" target="_blank" rel="noopener">Open demo seat B</a>${connectionHTML()}<div class="back-row"><button class="text-btn" data-go="collection">Collection</button></div></section>`;
}
function frontsHTML(interactive = true) {
  const r=state.room, me=r.seat, rival=1-me;
  return `<div class="fronts">${['Evidence','Response','People'].map((f,i)=>{const a=r.scores[me][f],b=r.scores[rival][f], status=a===b?'Tied':a>b?'You lead':'Rival leads';return `<button class="front front-${f.toLowerCase()} ${a>b?'front-led':b>a?'front-lost':''} ${state.front===f&&interactive?'selected':''}" data-action="front" data-id="${f}" aria-label="${f} front, you ${a}, rival ${b}" aria-pressed="${state.front===f}" ${!interactive||r.locked||!state.connected?'disabled':''}><h3><span>${['⌕','◇','⌘'][i]}</span>${f}</h3><div class="front-status">${status}</div><div class="front-score"><b class="you">${a}</b><span>–</span><b class="them">${b}</b></div><div class="score-track"><i style="flex:${a||1}"></i><i style="flex:${b||1}"></i></div><div class="score-labels"><span>You</span><span>${clean(r.names[rival]||'Rival')}</span></div></button>`;}).join('')}</div>`;
}
function playHTML(h, seat) {
  const r=state.room,p=h.plays[seat],effect=h.effects[seat];
  const total=Object.values(effect.delta).reduce((sum,v)=>sum+v,0), bonus=Math.max(0,total-2);
  const outcome=effect.outcome||'success';
  const status=outcome==='success'?'Ability activated':outcome==='partial'?'Ability partly activated':'Ability not activated';
  const feedback=p.evaluation?.feedback|| (outcome==='fail'?'Your decision did not connect clearly enough to the case.':'Your decision applied the card’s skill.');
  return `<article class="play outcome-${esc(outcome)} ${seat!==r.seat?'rival':''}"><span class="who">${seat===r.seat?'You':clean(r.names[seat])}</span><h3>${cardName(p.card)}</h3><span class="play-front">${clean(p.front)}</span><div class="influence-breakdown"><strong>+2 <span>Base</span></strong>${bonus?`<strong class="skill-bonus">+${bonus} <span>Ability</span></strong>`:''}</div><div class="effect-badge">${status}</div><p>${clean(feedback)}</p>${p.response?`<details><summary>Your decision</summary><p>“${clean(p.response)}”</p></details>`:''}<div class="delta">${Object.entries(effect.delta).filter(([,v])=>v).map(([f,v])=>`+${v} ${clean(f)}`).join(' · ')}</div></article>`;
}
function logHTML() {
  const r=state.room;
  return r.history.length?`<details class="history"><summary>Round history</summary>${r.history.map(h=>`<div class="history-entry"><h3>Round ${h.round}</h3><div class="plays">${playHTML(h,r.seat)}${playHTML(h,1-r.seat)}</div></div>`).join('')}</details>`:'';
}
function duelHTML() {
  const r=state.room;
  if(!r) return `<div class="loading">Connecting…<div class="back-row"><button class="text-btn" data-go="collection">Collection</button></div></div>`;
  if(r.phase==='lobby') return lobbyHTML();
  if(r.phase==='result') return resultsHTML();
  const current=r.deck.find(c=>c.id===state.playCard), locked=r.locked, canLock=current&&state.front&&state.connected&&r.opponent_online&&!locked;
  return `<div class="duel-head"><div><div class="eyebrow">Room ${r.code}</div><h1>The borrowed badge</h1></div><div class="duel-meta"><div class="round-pips">${[1,2,3,4].map(n=>`<i class="${n<=r.round?'on':''}"></i>`).join('')}</div><div>Round ${r.round} / 4 · ${connectionHTML()}</div></div></div>
  <section class="case-bar"><div class="case-copy"><span class="tag">Battle case</span><p>${clean(state.config.case.summary)}</p></div><details><summary>View clues</summary><div class="clue-list">${state.config.case.clues.map(c=>`<div><strong>${clean(c.title)}</strong><p>${clean(c.text)}</p></div>`).join('')}</div></details></section>
  <div class="player-line"><span class="accent">${clean(r.names[r.seat])} · You</span><span class="amber">${clean(r.names[1-r.seat])} · ${r.opponent_online?'Online':'Disconnected'}</span></div>${frontsHTML(r.phase==='choose')}
  ${r.phase==='reveal'?`<section class="round-reveal"><div class="section-head"><h2>Round ${r.round} resolved</h2><button class="btn primary" data-action="ready" ${r.ready||!state.connected?'disabled':''}>${r.ready?'Waiting…':'Next round'}</button></div><div class="plays">${playHTML(r.history.at(-1),r.seat)}${playHTML(r.history.at(-1),1-r.seat)}</div></section>`:
  `<div class="duel-controls"><h2>${locked?'Move locked':'Choose a card and front'}</h2><span class="pill ${r.opponent_locked?'cyan':''}">${r.opponent_locked?'Rival locked':'Rival choosing'}</span></div><div class="hand">${r.deck.map(c=>cardHTML(c,{click:'play-card',selected:c.id===state.playCard,disabled:locked||r.used.includes(c.id)||!state.connected,used:r.used.includes(c.id)&&(!r.own_play||r.own_play.card.id!==c.id)})).join('')}</div>
  <div class="commit-panel ${locked?'waiting':''}"><div class="commit-summary">${locked?`<strong>${cardName(r.own_play.card)}</strong><span>${clean(r.own_play.front)}</span><p class="sealed-response">“${clean(r.own_play.response||'Base influence only')}”</p>${r.evaluating?'Resolving move…':`Waiting for ${clean(r.names[1-r.seat])}…`}`:current?`<strong>${cardName(current)}</strong><span>${state.front?clean(state.front):'Choose a front'}</span>`:'Choose an unused card'}</div>${!locked&&current?`<div class="battle-writing"><label for="battle-response">${clean(current.prompt)}</label><textarea id="battle-response" maxlength="400" rows="2" placeholder="One tactical sentence">${esc(state.battleText)}</textarea><span class="micro muted">Ability · ${clean(current.ability_name)}</span></div>`:''}${!locked?`<button class="btn primary" id="lock-btn" data-action="lock" ${canLock?'':'disabled'}>${!r.opponent_online?'Waiting for rival':'Lock move'}</button>`:'<span class="pill amber pulse">Locked</span>'}</div>`}
  ${logHTML()}<div class="back-row"><button class="text-btn" data-go="collection">Collection</button></div>`;
}
function resultsHTML() {
  const r=state.room,result=r.result,win=result.winner,heading=win===null?'Draw':win===r.seat?'Victory':'Defeat';
  return `<section class="result-banner"><span class="pill ${win===r.seat?'cyan':''}">${heading}</span><h1>${heading}</h1></section>${frontsHTML(false)}<section class="result-insight"><div><h2>Your strategy</h2><ul class="strategy-list">${result.insights[r.seat].slice(0,3).map(o=>`<li>${clean(o.text)}</li>`).join('')}</ul></div><div><h2>Skills practised</h2><div class="skill-tags">${[...new Set(result.insights[r.seat].flatMap(o=>o.skills))].map(s=>`<span class="pill">${clean(s)}</span>`).join('')}</div></div></section><div class="section-head decisive-head"><h2>Decisive moves</h2></div>${result.decisive.map(n=>{const h=r.history.find(h=>h.round===n);return `<section class="history-entry"><h3>Round ${n}</h3><div class="plays">${playHTML(h,r.seat)}${playHTML(h,1-r.seat)}</div></section>`;}).join('')}<div class="result-actions"><button class="btn primary" data-action="rematch" ${r.rematch||!state.connected?'disabled':''}>${r.rematch?'Waiting…':r.opponent_rematch?'Accept rematch':'Rematch'}</button><button class="btn secondary" data-go="forge">New case</button><button class="text-btn" data-go="collection">Collection</button></div>${logHTML()}`;
}
function render() {
  const caseOpen=!!$('.case-bar details[open]');
  const focused=document.activeElement;
  const focusAction=focused?.dataset?.action, focusId=focused?.dataset?.id;
  const typing=focused?.id==='battle-response', cursor=typing?focused.selectionStart:0;
  const renders={home:homeHTML,forge:forgeHTML,reveal:revealHTML,collection:collectionHTML,room:duelHTML};
  $('#main').innerHTML=(renders[state.route]||homeHTML)();
  if(caseOpen&&$('.case-bar details'))$('.case-bar details').open=true;
  if(focusAction){const replacement=[...document.querySelectorAll('[data-action]')].find(el=>el.dataset.action===focusAction&&el.dataset.id===focusId&&!el.disabled);replacement?.focus({preventScroll:true});}
  if(typing&&$('#battle-response')){$('#battle-response').focus({preventScroll:true});$('#battle-response').setSelectionRange(cursor,cursor);}
  $('#collection-count').textContent=state.profile?.cards.length||0;
  $('#identity').textContent=state.profile?.nickname||'Guest';
  const profileView=location.hash==='#collection/profile';
  document.querySelectorAll('nav .nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.go===state.route&&!profileView||b.dataset.action==='battle-nav'&&state.route==='room'||b.dataset.action==='profile-nav'&&profileView));
}
async function routeChanged() {
  const [route,id]=location.hash.slice(1).split('/');
  state.route=['home','forge','collection','reveal','room'].includes(route)?route:'home';
  if(state.route!=='room') disconnect();
  try {
    if(state.route==='forge'&&state.profile&&!state.attempt){render();state.attempt=await api('/forge/start',{generate:false,known_good:true});}
    if(state.route==='collection'&&state.token) state.profile=await api('/me');
    if(state.route==='reveal') {state.card=state.profile?.cards.find(c=>c.id===id)||state.card;if(!state.card){nav('collection');return;}}
    if(state.route==='forge'&&state.attempt)state.reason=sessionStorage.getItem(`${key}-draft-${state.attempt.id}`)||state.attempt.response||'';
    render();
    if(state.route==='room') {const code=(id||sessionStorage.getItem(`${key}-room`)||'').toUpperCase();if(!code||!state.token){nav('collection');return;}connect(code);}
    window.scrollTo(0,0);
  } catch(e){toast(e.message,true);$('#main').innerHTML=`<div class="error-box">${clean(e.message)}<div class="back-row"><button class="btn secondary" data-go="home">Home</button></div></div>`;}
}
function disconnect() {
  clearTimeout(state.reconnect);clearInterval(state.ping);
  if(state.socket){state.socket.onclose=null;state.socket.close();state.socket=null;}
  state.connected=false;
}
function connect(code) {
  if(state.socket&&state.socket.readyState<=1&&state.room?.code===code)return;
  disconnect();
  if(state.room?.code!==code)state.room=null;
  sessionStorage.setItem(`${key}-room`,code);
  const ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/${code}`);
  state.socket=ws;
  ws.onopen=()=>{ws.send(JSON.stringify({token:state.token}));state.connected=true;state.ping=setInterval(()=>{if(ws.readyState===1)ws.send(JSON.stringify({type:'ping'}));},15000);};
  ws.onmessage=(event)=>{
    const msg=JSON.parse(event.data);
    if(msg.type==='error'){toast(msg.message,true);if(msg.fatal){disconnect();sessionStorage.removeItem(`${key}-room`);nav('collection');}return;}
    if(msg.type!=='state')return;
    const roundKey=`${msg.code}/${msg.match}/${msg.round}`;
    if(state.lastRound!==roundKey){state.playCard='';state.front='';state.battleText='';state.lastRound=roundKey;}
    if(msg.own_play){state.playCard=msg.own_play.card.id;state.front=msg.own_play.front;state.battleText=msg.own_play.response||'';}
    const caseOpen=!!$('.case-bar details[open]');
    state.room=msg;state.connected=true;if(state.route==='room'){render();if(caseOpen&&$('.case-bar details'))$('.case-bar details').open=true;}
  };
  ws.onclose=(event)=>{state.connected=false;state.socket=null;clearInterval(state.ping);if(state.route==='room'){render();if(event.code===4001){toast('This seat opened in another tab. Use Demo seat B for a second player.',true);}else state.reconnect=setTimeout(()=>connect(code),1500);}};
  ws.onerror=()=>{};
}
function sendMove(type) {
  if(!state.connected||state.socket?.readyState!==1){toast('Reconnecting. Your move has not been sent.',true);return;}
  const r=state.room;
  state.socket.send(JSON.stringify({type,match:r.match,round:r.round,card_id:state.playCard,front:state.front,response:state.battleText}));
}
async function createIdentity(nickname,demo=false) {
  const p=await api('/profile',{nickname,demo});state.token=p.token;localStorage.setItem(key,p.token);state.profile=p;state.attempt=null;
}
async function askQuestion(question) {
  if(state.busy)return;state.busy=true;state.question=question;render();
  try{const q=await api('/forge/ask',{attempt:state.attempt.id,question});state.attempt.questions=q.questions;state.question='';}catch(e){toast(e.message,true);}finally{state.busy=false;render();}
}
document.addEventListener('click',async event=>{
  if(event.target.closest('.skip')){event.preventDefault();$('#main').focus();return;}
  const go=event.target.closest('[data-go]');if(go){nav(go.dataset.go);return;}
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const {action,id}=button.dataset;
  try{
    if(action==='inspect'){
      if(state.openEvidence.has(id))state.openEvidence.delete(id);else{const seen=await api('/forge/inspect',{attempt:state.attempt.id,evidence:id});state.attempt.evidence=seen.evidence;state.openEvidence.add(id);}render();
    }else if(['new-case','generate-case','demo-case'].includes(action)){
      if(state.busy)return;state.busy=true;render();
      try{state.attempt=await api('/forge/start',{new:true,domain:state.domain,generate:action==='generate-case'&&state.config.ai,known_good:action==='demo-case'});state.reason='';state.question='';state.openEvidence.clear();if(state.attempt.message)toast(state.attempt.message);}finally{state.busy=false;render();}
    }
    else if(action==='ask'){await askQuestion(button.dataset.question);}
    else if(action==='battle-nav'){const code=sessionStorage.getItem(`${key}-room`);if(code)nav(`room/${code}`);else{nav('collection');toast('Create or join a room to battle.');}}
    else if(action==='profile-nav'){nav('collection/profile');setTimeout(()=>$('.decision-profile')?.scrollIntoView({behavior:'smooth'}),80);}
    else if(action==='select-card'){state.selectedCard=id;render();}
    else if(action==='view-card'){state.card=state.profile.cards.find(c=>c.id===id);nav(`reveal/${id}`);}
    else if(action==='create-room'){
      if(state.busy)return;state.busy=true;render();
      try{const room=await api('/rooms',{card_id:state.selectedCard});nav(`room/${room.code}`);}finally{state.busy=false;}
    }else if(action==='resume-room')nav(`room/${sessionStorage.getItem(`${key}-room`)}`);
    else if(action==='copy-code'){try{await navigator.clipboard.writeText(state.room.code);toast('Room code copied.');}catch{toast(`Room code: ${state.room.code}`);}}
    else if(action==='play-card'){state.playCard=id;state.battleText='';render();}
    else if(action==='front'){state.front=id;render();}
    else if(['lock','ready','rematch'].includes(action)){button.disabled=true;sendMove(action);}
  }catch(e){state.busy=false;toast(e.message,true);render();}
});
document.addEventListener('input',event=>{
  if(event.target.id==='reason'){state.reason=event.target.value;sessionStorage.setItem(`${key}-draft-${state.attempt.id}`,state.reason);}
  if(event.target.id==='battle-response')state.battleText=event.target.value;
  if(event.target.id==='question')state.question=event.target.value;
});
document.addEventListener('change',event=>{if(event.target.id==='case-domain')state.domain=event.target.value;});
document.addEventListener('submit',async event=>{
  event.preventDefault();const id=event.target.id;if(state.busy)return;
  if(id==='ask-form'){await askQuestion($('#question').value.trim());return;}
  if(id==='identity-form'){
    const name=$('#nickname').value.trim();state.busy=true;
    try{await createIdentity(name);state.attempt=await api('/forge/start',{generate:false,known_good:true});nav('forge');}catch(e){toast(e.message,true);}finally{state.busy=false;render();}
  }else if(id==='forge-form'){
    state.busy=true;render();
    try{const result=await api('/forge',{attempt:state.attempt.id,response:state.reason.trim()});
      if(result.card){state.card=result.card;state.profile=await api('/me');sessionStorage.removeItem(`${key}-draft-${state.attempt.id}`);state.attempt=null;state.reason='';state.openEvidence.clear();nav(`reveal/${result.card.id}`);}
      else{state.attempt={...state.attempt,assessment:result.assessment,can_retry:result.can_retry,retry_count:result.retry_count};toast(result.can_retry?'Make the decision more specific.':'Start a new case to try again.');}
    }catch(e){toast(e.message,true);}finally{state.busy=false;render();}
  }else if(id==='join-form'){
    const code=$('#room-code').value.trim().toUpperCase();state.busy=true;
    try{await api(`/rooms/${encodeURIComponent(code)}/join`,{card_id:state.selectedCard});nav(`room/${code}`);}catch(e){toast(e.message,true);}finally{state.busy=false;}
  }
});
window.addEventListener('hashchange',routeChanged);
window.addEventListener('online',()=>{if(state.route==='room'&&!state.connected)connect(sessionStorage.getItem(`${key}-room`));});
async function boot(){
  try{
    state.config=await api('/config');
    if(state.token){try{state.profile=await api('/me');state.attempt=state.profile.attempt;}catch(e){if(e.status!==401)throw e;state.token='';localStorage.removeItem(key);}}
    if(location.pathname==='/demo'){
      if(!state.profile||!state.profile.cards.length)await createIdentity(slot==='B'?'Orion':'Nova',true);
      state.selectedCard=state.profile.cards[0].id;
      const room=params.get('room');
      if(room&&!location.hash){await api(`/rooms/${encodeURIComponent(room)}/join`,{card_id:state.selectedCard});nav(`room/${room}`);return;}
      if(!location.hash){nav('collection');return;}
    }
    await routeChanged();
  }catch(e){$('#main').innerHTML=`<section class="error-box"><h2>Connection lost</h2><p>${clean(e.message)}</p><button class="btn primary" onclick="location.reload()">Reconnect</button></section>`;}
}
boot();
