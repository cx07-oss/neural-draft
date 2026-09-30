'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s = '') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const params = new URLSearchParams(location.search);
const slot = params.get('pilot') === 'B' ? 'B' : params.get('pilot') === 'A' ? 'A' : 'default';
const key = `neural-draft-${slot}`;
const state = {token: localStorage.getItem(key) || '', profile: null, config: null, route: 'home', selectedCard: '',
  attempt: null, openEvidence: new Set(), domain: 'random', battleText: '', reason: '', question: '', busy: false,
  room: null, socket: null, connected: false, reconnect: null, ping: null,
  playCard: '', front: '', lastRound: '', card: null, notice: ''};
let toastTimer;
function toast(message, error = false) { const t = $('#toast'); t.textContent = message; t.className = `toast ${error ? 'error' : ''}`; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, error ? 7500 : 4000); }
async function api(path, body) {
  const response = await fetch(`/api${path}`, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json','X-Player': state.token}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  let data; try {data = await response.json();} catch {throw new Error('The server could not respond. Please try again.');}
  if (!response.ok) {const error=new Error(typeof data.detail === 'string' ? data.detail : 'Check your input and try again.');error.status=response.status;throw error;}
  return data;
}
function nav(route) { if (location.hash === `#${route}`) routeChanged(); else location.hash = route; }
function art(kind, seed = '', evolution = '') {
  const rotation = [...seed].reduce((sum, c) => sum + c.charCodeAt(0), 0) % 30 - 15;
  const shapes = {
    Investigate: `<circle cx="120" cy="85" r="47"/><circle cx="120" cy="85" r="30" stroke-dasharray="4 7"/><path d="m77 129-20 20m106-21 20 20M120 16v18M51 85h20M169 85h20"/><path d="m120 49 31 36-31 36-31-36z" fill="currentColor" fill-opacity=".08"/><circle cx="120" cy="85" r="7" fill="currentColor"/>`,
    Contain: `<path d="m120 24 50 22v46q0 33-50 60-50-27-50-60V46z" fill="currentColor" fill-opacity=".08"/><path d="m120 41 34 15v34q0 23-34 43-34-20-34-43V56zM120 24v109M70 75h100"/><circle cx="120" cy="82" r="14"/><path d="M42 49v70m156-70v70" stroke-dasharray="3 6"/>`,
    Challenge: `<path d="m120 22 61 63-61 64-61-64z" fill="currentColor" fill-opacity=".05"/><path d="m120 42 41 43-41 43-41-43zM120 22v23m0 80v24M59 85h23m76 0h23"/><path d="m130 49-28 42h22l-13 32 31-48h-24z" fill="currentColor" fill-opacity=".6"/>`,
    Coordinate: `<path d="m120 34 55 83H65zM65 117l55-32 55 32M120 34v51"/><circle cx="120" cy="85" r="24" fill="currentColor" fill-opacity=".08"/><circle cx="120" cy="34" r="12"/><circle cx="65" cy="117" r="12"/><circle cx="175" cy="117" r="12"/><circle cx="120" cy="85" r="7" fill="currentColor"/><circle cx="120" cy="85" r="69" stroke-dasharray="2 9"/>`
  };
  const aura = evolution === 'Luminous' ? '<circle cx="120" cy="85" r="72" opacity=".55" stroke-dasharray="1 7"/><path d="m40 36 4-8 4 8-4 8zm152 98 4-8 4 8-4 8z" fill="currentColor" opacity=".8"/>' : evolution === 'Focused' ? '<circle cx="120" cy="85" r="64" opacity=".3" stroke-dasharray="25 12"/>' : '';
  return `<svg class="card-art" viewBox="0 0 240 172" fill="none" aria-hidden="true"><g stroke="currentColor" stroke-width="1.1" transform="rotate(${rotation} 120 85)"><circle cx="120" cy="85" r="78" opacity=".12"/><path d="M12 85h30m156 0h30M120 3v10m0 144v12" opacity=".3"/>${aura}${shapes[kind] || shapes.Investigate}<g opacity=".4"><path d="M20 20h18M20 20v18m200-18h-18m18 0v18M20 150h18m-18 0v-18m200 18h-18m18 0v-18"/></g></g></svg>`;
}
function cardHTML(card, opts = {}) {
  const tag = opts.click ? 'button' : 'article';
  return `<${tag} class="skill-card rarity-${esc(card.rarity||'COMMON')} ${esc(card.archetype)} ${opts.selected ? 'selected' : ''}" ${opts.click ? `data-action="${opts.click}" data-id="${esc(card.id)}" aria-pressed="${!!opts.selected}" aria-label="${esc(card.name)} — ${esc(card.archetype)}"` : ''} ${opts.disabled ? 'disabled' : ''}>
    <div class="card-top"><span>${esc(card.archetype.toUpperCase())}</span><span class="rarity-label">${card.evolution==='Starter'?'STARTER':esc(card.rarity||'COMMON')}</span></div>
    ${art(card.archetype, card.id, card.evolution)}<h3>${esc(card.name)}</h3><div class="card-skill">${esc(card.skill)}</div>
    <div class="ability-title">${esc(card.ability_name||card.archetype)}</div><p class="card-effect">${esc(card.effect)}</p><p class="card-flavour">“${esc(card.flavour)}”</p>
    <div class="card-bottom"><span>${esc(card.evolution)}</span><span>${card.demo ? 'DEMO ISSUE' : card.evolution === 'Starter' ? 'CORE / 05' : 'FORGED / YOU'}</span></div>${opts.used ? '<div class="used-label">DEPLOYED</div>' : ''}</${tag}>`;
}
const sample = {id:'landing',name:'Ghost Protocol',archetype:'Investigate',skill:'Independent verification',effect:'Base 2. Success: +1 here and +1 on your weakest other front. Partial: +1 here.',ability_name:'Cross-Reference',rarity:'RARE',flavour:'Two signals. One decision you can defend.',evolution:'Luminous'};
function homeHTML() {
  return `<section class="hero"><div class="hero-copy"><div class="eyebrow">THE NEXT MOVE IS YOURS</div><h1>Your judgement.<br>Your card.<br><span>Your next move.</span></h1><p class="intro">Neural-Draft is a competitive game where real-world decisions become the cards you play. Outsmart a rival. Forge your next edge.</p><div class="button-row"><button class="btn primary" data-go="forge">Enter the Solo Forge <span>↗</span></button><a class="btn secondary" href="/demo?pilot=A">Quick duel ↗</a></div><p class="subnote">SIX CASE WORLDS <span class="muted">/</span> APPLY → FORGE → BATTLE → ADAPT</p></div><div class="hero-art"><svg class="constellation" viewBox="0 0 500 500" fill="none" aria-hidden="true"><g stroke="#527587" stroke-width=".6"><path d="m40 70 160 30 110-70 130 110-30 220-170 95L50 310zM40 70l200 385m-190-145L440 140M200 100l210 260M50 310l150-210 40 355"/><circle cx="250" cy="250" r="202" stroke-dasharray="2 10"/></g><g fill="#77ebe5"><circle cx="40" cy="70" r="3"/><circle cx="440" cy="140" r="3"/><circle cx="410" cy="360" r="3"/><circle cx="50" cy="310" r="3"/><circle cx="240" cy="455" r="3"/></g></svg><div class="ghost-card"></div>${cardHTML(sample)}<div class="hero-tag">✧ EARNED THROUGH ACTION</div><div class="orbit-label">YOUR EXPERIENCE. YOUR SIGNATURE.</div></div></section>
  <section class="step-strip" aria-label="How it works"><div class="step"><span class="step-num">01</span><div><h3>Face the situation</h3><p>Read the signals. Ask a question.<br>Make the call.</p></div></div><div class="step"><span class="step-num">02</span><div><h3>Forge your proof</h3><p>Write your move. Discover your signature.<br>Stabilise a card. Find an unexpected edge.</p></div></div><div class="step"><span class="step-num">03</span><div><h3>Play what you know</h3><p>Two players. Three fronts. Four rounds.<br>Apply your skill in a new case.</p></div></div></section>
  <div class="quick-bar"><p><strong>Short on time? Try the live duel.</strong><br>Quick demo includes a clearly labelled practice card. Open one seat in each browser.</p><div class="button-row"><a class="btn small secondary" href="/demo?pilot=A">Demo seat A ↗</a><a class="btn small secondary" href="/demo?pilot=B" target="_blank" rel="noopener">Demo seat B ↗</a></div></div>`;
}
function identityHTML() {
  return `<section class="panel form-panel"><div class="eyebrow">ESTABLISH YOUR SIGNAL</div><h1>What should we<br>call you?</h1><p>Your nickname appears on your card and at the duel table.</p><form id="identity-form"><div class="form-field"><label for="nickname">Nickname</label><input id="nickname" name="nickname" required minlength="1" maxlength="18" autocomplete="nickname" placeholder="e.g. Nova"></div><button class="btn primary wide" ${state.busy?'disabled':''}>${state.busy?'Preparing…':'Begin the simulation →'}</button></form><p class="saved-note">Saved to this local server. This browser remembers your profile; nicknames are not passwords.</p></section>`;
}
function rubricHTML() {
  return `<details class="panel rubric" open><summary>Your rubric · visible from the start</summary>${state.config.rubric.map(r=>`<div class="rubric-row"><strong>${esc(r.title)}</strong><ul>${r.levels.map(l=>`<li>${esc(l)}</li>`).join('')}</ul></div>`).join('')}<p class="small-copy muted">0–2 per skill. Higher scores evolve the visual theme, never the card's power.</p></details>`;
}
function forgeHTML() {
  if (!state.profile) return identityHTML();
  if (!state.attempt) return '<div class="loading">Opening a case from the archive…</div>';
  const a=state.attempt,c=a.scenario,q=a.questions?.at(-1),review=a.assessment;
  return `<div class="breadcrumb"><span class="current">01 / THE CASE</span><span>—</span><span>02 / YOUR SIGNATURE</span><span>—</span><span>03 / THE ARENA</span></div>
  <div class="case-switch"><label for="case-domain">Case world</label><select id="case-domain"><option value="random">Surprise me</option>${state.config.domains.map(d=>`<option value="${d}" ${state.domain===d?'selected':''}>${esc(d)}</option>`).join('')}</select><button class="btn small secondary" data-action="new-case" ${state.busy?'disabled':''}>New case ↗</button><button class="text-btn" data-action="generate-case" ${state.busy||!state.config.ai?'disabled':''}>Generate with ${esc(state.config.ai_status?.provider||'AI')}</button><button class="text-btn" data-action="demo-case" ${state.busy?'disabled':''}>Demo case</button></div>
  <div class="section-head"><div class="page-intro"><div class="eyebrow">${esc(c.domain)} / ${esc(c.source)}</div><h1>${esc(c.title)}</h1><p>${esc(c.brief)}</p></div><span class="pill amber">${esc(c.difficulty)}</span></div>
  <div class="incident-pressure"><span>◷ ${esc(c.time_pressure)}</span><p>${esc(c.stakes)}</p></div>
  <div class="assessment-mode"><i class="status-dot"></i>${state.config.ai?`${esc(state.config.ai_status?.provider||'Neural')} analysis ready · local fallback on standby`:'Local analysis · approximate pattern matching'}</div>
  <div class="forge-grid"><section><div class="section-head"><h3>Signals on the desk</h3><span class="tag">${a.evidence.length} / ${c.evidence.length} OPENED</span></div><div class="evidence-list">${c.evidence.map(e=>{const open=state.openEvidence.has(e.id),seen=a.evidence.includes(e.id);return `<article class="panel evidence ${open?'open':''}"><button class="inspect" data-action="inspect" data-id="${esc(e.id)}" aria-expanded="${open}" ${state.busy?'disabled':''}><div><span class="tag">${esc(e.id)} / CASE RECORD</span><h3>${esc(e.title)}</h3></div><span class="read-label">${seen?'✓ READ':'+ INSPECT'}</span></button>${open?`<div class="evidence-body"><p>${esc(e.text)}</p><details><summary>How reliable is this signal?</summary><p>${esc(e.reliability)} confidence in the record. A reliable record can still leave its cause uncertain.</p></details></div>`:''}</article>`;}).join('')}</div></section>
  <aside class="panel"><div class="character-head"><span class="avatar">${esc(c.characters[0].name.split(' ').map(n=>n[0]).join(''))}</span><div><h3>${esc(c.characters[0].name)}</h3><p>${esc(c.characters[0].role)}</p></div></div><div class="chat">${q?`<p class="asked">You: ${esc(q.question)}</p><p>${esc(q.answer)}</p>`:`<p>“${esc(c.characters[0].initial_message)}”</p>`}</div><form id="ask-form" class="chat-form"><label class="hidden" for="question">Ask the stakeholder</label><input id="question" placeholder="Ask about a case detail…" maxlength="240" minlength="2" required value="${esc(state.question)}"><button class="btn small secondary" aria-label="Ask stakeholder" ${state.busy?'disabled':''}>↑</button></form><span class="micro muted">CASE-GROUNDED CHARACTER · AUTHORED RESPONSE ROUTING</span>${c.characters.slice(1).map(x=>`<hr class="divider"><strong>${esc(x.name)} · ${esc(x.role)}</strong><p>${esc(x.initial_message)}</p>`).join('')}<details class="forge-rubric"><summary>What stabilises a card?</summary><p>A concrete action, evidence that matters, a proportionate risk decision, and room to adapt. Your reasoning shapes the signature; rarity never grants unrestricted power.</p></details></aside></div>
  ${review?.verdict==='fail'?`<section class="unstable panel" role="status"><div class="eyebrow">FORGE UNSTABLE</div><h2>The signal needs a clearer shape.</h2><p>${esc(review.feedback)}</p><p class="small-copy">${a.can_retry?'One quick retry: name a case detail and the risk your action addresses.':'Both attempts are used. Take what you noticed into a new case.'}</p><p class="small-copy muted">${esc(review.notice)}</p></section>`:''}
  <section class="panel decision-panel"><div class="eyebrow">NO PRESET ANSWERS</div><h2>What would you do?</h2><form id="forge-form"><label class="hidden" for="reason">Your decision</label><textarea id="reason" maxlength="1200" rows="4" placeholder="Make your call in 1–4 sentences. Say what you would do, which detail matters, and why." ${state.busy||!a.can_retry?'disabled':''}>${esc(state.reason)}</textarea><div class="decision-footer"><span class="small-copy muted">Fictional game case · a card records a decision, not a mastery score.</span><button id="forge-submit" class="btn primary" ${state.busy||!a.can_retry?'disabled':''}>${state.busy?'Working on the signal…':review?'Stabilise on retry ✧':'Forge my decision ✧'}</button></div></form></section>`;
}
function provenanceHTML(card) {
  const p=card.provenance, review=card.assessment;
  if (!p) return '';
  if(p.version===3) return `<div class="notice">${esc(review.notice)}</div><div class="forge-verdict ${esc(review.verdict)}">${esc(review.verdict.toUpperCase())} · ${esc(card.rarity)} SIGNATURE</div><dl class="provenance"><dt>Origin</dt><dd>${esc(card.source_scenario)} · ${esc(card.domain)}</dd><dt>Your decision</dt><dd>“${esc(p.reason)}”</dd><dt>Grounded citation</dt><dd>“${esc(review.cited_player_text)}”</dd><dt>Evidence used</dt><dd>${review.evidence_ids.map(id=>esc(p.evidence_snapshot.find(e=>e.id===id)?.title||id)).join(' · ')||'No opened record cited.'}</dd></dl><details><summary>Forge analysis details</summary><div class="analysis-metrics">${['reasoning_score','evidence_use','risk_awareness','adaptability'].map(k=>`<span>${esc(k.replaceAll('_',' '))}<b>${review[k]} / 100</b></span>`).join('')}</div><p class="small-copy">Confidence ${Math.round(review.confidence*100)}% · ${review.mode==='local'?'approximate local pattern match':'model estimate'}. Rarity follows the demonstrated pattern, not a score threshold.</p></details>`;
  const legacyActions={verify:'Pause. Verify. Preserve.',isolate:'Isolate the test laptops',install:'Trust the urgent update'};
  const legacyEvidence={request:'An urgent favour',signature:'A signature out of place',scope:'The blast radius'};
  const actionTitle=p.action_title||legacyActions[p.action]||p.action;
  const evidenceTitles=p.evidence_titles||p.inspected.map(id=>legacyEvidence[id]||id);
  return `<div class="notice">${esc(review.notice)}</div>${review.mode!=='demo'?`<div class="score-grid">${state.config.rubric.map(r=>`<div class="score-box"><strong>${review.scores[r.key]}<span> / 2</span></strong><span>${r.title}</span></div>`).join('')}</div><dl class="provenance"><dt>Cited player action</dt><dd>${esc(actionTitle)}${p.focus?` · ${p.focus==='claim'?'Test approval claim':'Verify source'}`:''}${!p.version?' (original incident)':''}</dd><dt>Evidence inspected</dt><dd>${evidenceTitles.length?evidenceTitles.map(esc).join(' · '):'No evidence was opened.'}</dd><dt>Your recorded reason</dt><dd>“${esc(p.reason)}”</dd></dl><p class="small-copy muted">${review.mode==='ai'?'Model confidence':'Rule-match confidence'}: ${Math.round(review.confidence*100)}%. ${review.mode==='offline'?'The free-text reason was not scored.':''}</p>`:''}`;
}
function skillLink(card) {
  return `${card.demo?'Practice issue. ':''}${card.prompt||state.config.abilities[card.ability_id]?.prompt||'Apply the same judgement in the next case.'} Your base influence always lands; the written decision activates only the fixed skill effect.`;
}
function earnedHTML(card) {
  return `${card.demo?'':'<span class="tag">FORGED BECAUSE</span>'}<p class="earned-record">${esc(card.forged_because||(card.demo?'Demo issue · no behaviour assessed.':'Legacy signature · its original decision record is preserved.'))}</p>`;
}
function frameworkHTML(cards=[]) {
  const earned=cards.filter(c=>!c.demo);
  const found=new Set(earned.flatMap(c=>[c.archetype.toLowerCase(),c.pattern]).filter(id=>state.config.patterns.some(p=>p.id===id)));
  return `<section class="panel decision-profile"><div class="eyebrow">FOUR RESPONSES TO UNCERTAINTY</div><div class="framework-grid">${Object.entries(state.config.responses).map(([kind,text])=>`<div><strong>${esc(kind)}</strong><p>${esc(text)}</p>${state.route==='collection'?`<span class="tag">${earned.filter(c=>c.archetype===kind).length} FORGED</span>`:''}</div>`).join('')}</div>${state.route==='collection'?`<h3>Your Decision Profile</h3><p class="small-copy">Counts describe your cards, not a personality or mastery score. Demo issues are excluded.</p><details class="patterns"><summary>Reasoning patterns discovered · ${found.size}</summary><div class="pattern-grid">${state.config.patterns.map(p=>`<div class="pattern ${found.has(p.id)?'discovered':''}"><strong>${found.has(p.id)?'✓':p.available?'◇':'⊘'} ${esc(p.label)}</strong><span>${esc(p.kind)} · ${found.has(p.id)?'Discovered':p.available?'Undiscovered · try another decision':'Locked · future case'}</span></div>`).join('')}</div><p class="small-copy">Different written approaches can reveal different signatures. Classified opportunities are discovered through play; there is no score-to-rarity ladder.</p></details>`:''}</section>`;
}
function revealHTML() {
  const card=state.card; if (!card) return '<div class="loading">Loading your card…</div>';
  return `<div class="breadcrumb"><span>01 / SIMULATION</span><span>—</span><span class="current">02 / FORGED</span><span>—</span><span>03 / PLAY</span></div><section class="reveal-layout"><div><div class="reveal-stage">${cardHTML(card)}</div><p class="small-copy muted" style="text-align:center">PERSONAL SIGNATURE / ${esc(card.id.slice(0,8).toUpperCase())}</p></div><div class="reveal-copy"><div class="eyebrow">✧ ${card.demo?'PRACTICE SIGNAL ISSUED':'YOUR DECISION HAS A NEW FORM'}</div><h1>${card.demo?'Ready to practise.':'A skill worth keeping.'}</h1>${earnedHTML(card)}<div class="tag">FORGE ANALYSIS</div><p>${esc(card.assessment.feedback)}</p>${provenanceHTML(card)}<div class="skill-link"><span class="tag">WHY THIS ABILITY</span><p>${esc(skillLink(card))}</p></div><p class="small-copy muted">${esc(card.rarity||'COMMON')} reflects a reasoning pattern, not intelligence. Base influence and ability budgets stay bounded across all rarities.</p><div class="button-row"><button class="btn primary" data-go="collection">Play this signature →</button><button class="text-btn" data-go="forge">Try another decision</button></div><p class="saved-note">✓ Card and evidence saved in your local collection.</p></div></section>${frameworkHTML()}`;
}
function collectionHTML() {
  if(!state.profile) return identityHTML();
  const cards=state.profile.cards;
  if(!cards.length) return `<section class="empty"><div class="eyebrow">YOUR COLLECTION</div><h1>Your first signal<br>is waiting.</h1><p>A two-minute decision becomes a card you can play.</p><button class="btn primary" data-go="forge">Enter the Solo Forge →</button></section>`;
  if(!cards.some(c=>c.id===state.selectedCard)) state.selectedCard=cards[0].id;
  return `<div class="section-head"><div><div class="eyebrow">THE PROOF IS IN YOUR PLAY</div><h2>Your collection</h2><p class="small-copy" style="margin-top:12px">${cards.length} personal ${cards.length===1?'card':'cards'} · Select one to bring into the duel.</p></div><button class="btn small secondary" data-go="forge">+ Forge another</button></div>${frameworkHTML(cards)}<div class="collection-layout"><section><div class="collection-cards">${cards.map(c=>`<div class="collection-item">${cardHTML(c,{click:'select-card',selected:c.id===state.selectedCard})}${earnedHTML(c)}<p class="card-origin">${esc(c.domain||'Original case')} · ${esc(c.source_scenario||'Practice / legacy issue')}${c.forged_at?`<br>Forged ${esc(new Date(c.forged_at).toLocaleDateString())}`:''}</p><button class="text-btn" data-action="view-card" data-id="${c.id}">View why this card was earned ↗</button></div>`).join('')}</div><p class="saved-note">✓ Saved in SQLite under ${esc(state.profile.nickname)}. This browser retains your private profile token.</p></section><aside class="panel play-panel"><div class="eyebrow">YOUR NEXT RIVAL</div><h2>A new case.<br>The same skill.</h2><p>Take your selected card and five starter cards into a four-round duel.</p><div class="pill cyan">2 PLAYERS · 3 FRONTS · 4 ROUNDS</div><button class="btn primary wide" data-action="create-room" ${state.busy?'disabled':''}>Create a room →</button><hr class="divider"><label for="room-code">Have a room code?</label><form id="join-form" class="join-form"><input id="room-code" placeholder="ABCDE" maxlength="5" minlength="5" required autocomplete="off" aria-label="Room code"><button class="btn secondary small" ${state.busy?'disabled':''}>Join</button></form><hr class="divider"><details><summary>How the duel works</summary><p>Choose an unused card and a front, write a tactical sentence, then seal it secretly. Both plays reveal together. Lead two fronts after round four to win. If each player leads one and the third is tied, total influence breaks the split; otherwise it's a draw.</p><p>Write one tactical sentence before sealing a move. Success, partial or failure changes only the fixed skill effect; base 2 always lands. Rare variants trade conditions and placement, not bigger budgets.</p></details>${sessionStorage.getItem(`${key}-room`)?'<button class="text-btn" style="margin-top:18px" data-action="resume-room">Return to your last room ↗</button>':''}</aside></div>`;
}
function connectionHTML() {return `<span class="connection ${state.connected?'':'offline'}">● ${state.connected?'LIVE CONNECTION':'RECONNECTING…'}</span>`;}
function lobbyHTML() {
  const r=state.room;
  return `<section class="lobby"><div class="eyebrow">YOUR TABLE IS READY</div><h1>Good decisions<br>deserve a worthy rival.</h1><div class="panel"><span class="tag">SHARE THIS ROOM CODE</span><div class="room-code">${r.code}</div><button class="btn small secondary" data-action="copy-code">Copy room code</button><div class="lobby-slots"><div class="lobby-slot"><i class="status-dot"></i>${esc(r.names[0])}<p>SEAT A · READY</p></div><div class="lobby-slot"><span class="muted pulse">Waiting for player…</span><p>SEAT B · OPEN</p></div></div><p>In another browser, open this app, choose <strong>Demo seat B</strong> or forge a card, then enter <strong>${r.code}</strong> in Collection.</p><a class="btn secondary" href="/demo?pilot=B&room=${r.code}" target="_blank" rel="noopener">Open demo seat B ↗</a><p class="subnote">On another device, use this server's LAN address.</p>${connectionHTML()}</div><div class="back-row"><button class="text-btn" data-go="collection">← Back to collection</button></div></section>`;
}
function frontsHTML(interactive = true) {
  const r=state.room, me=r.seat, rival=1-me;
  return `<div class="fronts">${['Evidence','Response','People'].map((f,i)=>{const a=r.scores[me][f],b=r.scores[rival][f], status=a===b?'Front tied':a>b?'You lead':'Rival leads';return `<button class="front ${a>b?'front-led':b>a?'front-lost':''} ${state.front===f&&interactive?'selected':''}" data-action="front" data-id="${f}" aria-label="${f} front, you ${a}, rival ${b}" aria-pressed="${state.front===f}" ${!interactive||r.locked||!state.connected?'disabled':''}><span class="tag">FRONT / 0${i+1}</span><h3>${f}<span class="muted">${['⌕','◇','⌘'][i]}</span></h3><div class="front-status">${status}</div><div class="front-score"><b class="you">${a.toString().padStart(2,'0')}</b><span class="muted">:</span><b class="them">${b.toString().padStart(2,'0')}</b></div><div class="score-track"><i style="flex:${a||1}"></i><i style="flex:${b||1}"></i></div><div class="score-labels"><span>YOU</span><span>${esc(r.names[rival]||'RIVAL')}</span></div></button>`;}).join('')}</div>`;
}
function playHTML(h, seat) {
  const r=state.room,p=h.plays[seat],effect=h.effects[seat];
  return `<div class="play outcome-${esc(effect.outcome||'success')} ${seat!==r.seat?'rival':''}"><span class="who">${seat===r.seat?'YOU':esc(r.names[seat])} → ${esc(p.front).toUpperCase()}</span><h3>${esc(p.card.name)}</h3><p class="small-copy">Decision: ${esc(p.response||'No written rationale')}</p><span class="effect-badge">${esc((effect.outcome||'success').toUpperCase())}</span><p>${esc(effect.reason)}</p><p class="micro muted">${esc(p.evaluation?.notice||'')}</p><div class="delta">${Object.entries(effect.delta).filter(([,v])=>v).map(([f,v])=>`+${v} ${f}`).join(' / ')}</div></div>`;
}
function logHTML() {
  const r=state.room;
  return r.history.length?`<details class="history"><summary>Round history · ${r.history.length} revealed</summary>${r.history.map(h=>`<div class="history-entry"><h3>Round ${h.round}</h3><div class="plays">${playHTML(h,r.seat)}${playHTML(h,1-r.seat)}</div></div>`).join('')}</details>`:'';
}
function duelHTML() {
  const r=state.room;
  if(!r) return `<div class="loading">Connecting to your table…<div class="back-row"><button class="text-btn" data-go="collection">Return to collection</button></div></div>`;
  if(r.phase==='lobby') return lobbyHTML();
  if(r.phase==='result') return resultsHTML();
  const current=r.deck.find(c=>c.id===state.playCard), locked=r.locked, canLock=current&&state.front&&state.connected&&r.opponent_online&&!locked;
  return `<div class="duel-head"><div><div class="eyebrow" style="margin:0">THE ARENA / ROOM ${r.code}</div><h1>The borrowed badge</h1></div><div class="duel-meta"><div class="round-pips">${[1,2,3,4].map(n=>`<i class="${n<=r.round?'on':''}"></i>`).join('')}</div><div>ROUND ${r.round} / 4 · ${connectionHTML()}</div></div></div>
  <section class="panel case-bar"><div class="case-copy"><span class="tag">NEW CONTEXT / SAME JUDGEMENT</span><p style="margin-top:8px">${esc(state.config.case.summary)}</p></div><details><summary>Inspect the case file · 4 clues</summary><div class="clue-list">${state.config.case.clues.map(c=>`<div><strong>${c.title}</strong><p>${c.text}</p></div>`).join('')}</div></details></section>
  <div class="score-labels"><span class="accent">${esc(r.names[r.seat])} / YOU</span><span class="amber">${esc(r.names[1-r.seat])} / ${r.opponent_online?'CONNECTED':'DISCONNECTED · WAITING FOR RETURN'}</span></div>${frontsHTML(r.phase==='choose')}
  ${r.phase==='reveal'?`<section class="round-reveal"><div class="section-head"><div><div class="eyebrow" style="margin-bottom:8px">SIMULTANEOUS REVEAL</div><h2>Round ${r.round} resolved.</h2></div><button class="btn primary" data-action="ready" ${r.ready||!state.connected?'disabled':''}>${r.ready?'Waiting for rival…':r.opponent_ready?'Rival ready · next round →':'Next round →'}</button></div><div class="plays">${playHTML(r.history.at(-1),r.seat)}${playHTML(r.history.at(-1),1-r.seat)}</div></section>`:
  `<div class="duel-controls"><div><h3>${locked?'Move sealed.':'1. Choose a card. 2. Choose a front.'}</h3><p>${locked?'Your choice stays hidden until your rival locks in.':'3. Justify the move in one sentence. Base 2 always lands.'}</p></div><span class="pill ${r.opponent_locked?'cyan':''}">${r.opponent_locked?'✓ RIVAL LOCKED':'RIVAL IS CHOOSING'}</span></div><div class="hand">${r.deck.map(c=>cardHTML(c,{click:'play-card',selected:c.id===state.playCard,disabled:locked||r.used.includes(c.id)||!state.connected,used:r.used.includes(c.id)&&(!r.own_play||r.own_play.card.id!==c.id)})).join('')}</div>
  <div class="commit-panel ${locked?'waiting':''}"><div class="commit-summary">${locked?`<strong>◈ LOCKED · ${esc(r.own_play.card.name)}</strong><br>${esc(r.own_play.front)}<p class="sealed-response">“${esc(r.own_play.response||'No written rationale')}”</p><br>${r.evaluating?'Interpreting your sealed decision…':`Waiting for ${esc(r.names[1-r.seat])}${r.opponent_online?'…':' to reconnect…'}`}`:current?`<strong>${esc(current.name)}</strong><br>${state.front?`Deploying to ${esc(state.front)}`:'Select a front above to place your influence.'}`:'Select an unused card from your hand to begin.'}</div>${!locked&&current?`<div class="battle-writing"><label for="battle-response">${esc(current.prompt)}</label><textarea id="battle-response" maxlength="400" rows="2" placeholder="Your tactical call. One sentence.">${esc(state.battleText)}</textarea><span class="micro muted">SKILL EFFECT: ${esc(current.ability_name)} · NO RATIONALE = BASE ONLY</span></div>`:''}${!locked?`<button class="btn primary" id="lock-btn" data-action="lock" ${canLock?'':'disabled'}>${!r.opponent_online?'Waiting for rival':'Lock in move ◈'}</button>`:'<span class="pill amber pulse">SEALED</span>'}</div>`}
  ${logHTML()}<div class="back-row"><button class="text-btn" data-go="collection">← Collection</button><span class="small-copy muted"> · Your seat and locked move are kept if you reconnect.</span></div>`;
}
function resultsHTML() {
  const r=state.room,result=r.result,win=result.winner,heading=win===null?'A worthy draw.':win===r.seat?'Your judgement held.':`${esc(r.names[win])} takes the match.`;
  return `<section class="result-banner"><div class="eyebrow">FOUR ROUNDS. A NEW PERSPECTIVE.</div><span class="pill cyan">${win===null?'DRAW':win===r.seat?'VICTORY':'MATCH COMPLETE'}</span><h1>${heading}</h1><p>${esc(result.reason)}</p></section>${frontsHTML(false)}<div class="panel result-insight"><div class="eyebrow" style="margin-bottom:10px">HOW YOU PLAYED / ${esc(r.names[r.seat]).toUpperCase()}</div><ul class="strategy-list">${result.insights[r.seat].map(o=>`<li>${esc(o.text)}</li>`).join('')}</ul><div class="tag">SKILLS PRACTISED</div><div class="skill-tags">${[...new Set(result.insights[r.seat].flatMap(o=>o.skills))].map(s=>`<span class="pill">${esc(s)}</span>`).join('')}</div></div><div class="section-head"><h2 style="font-size:24px">Moves that shaped the duel</h2><span class="tag">LARGEST INFLUENCE SWINGS</span></div>${result.decisive.map(n=>{const h=r.history.find(h=>h.round===n);return `<section class="history-entry"><h3>Round ${n} · ${Math.abs(Object.values(h.effects[0].delta).reduce((a,b)=>a+b,0)-Object.values(h.effects[1].delta).reduce((a,b)=>a+b,0))} influence swing</h3><div class="plays">${playHTML(h,r.seat)}${playHTML(h,1-r.seat)}</div></section>`;}).join('')}<div class="result-banner"><div class="button-row"><button class="btn primary" data-action="rematch" ${r.rematch||!state.connected?'disabled':''}>${r.rematch?'Rematch requested · waiting…':r.opponent_rematch?'Accept rematch ↗':'Play a rematch ↗'}</button><button class="btn secondary" data-go="forge">Forge a different response →</button><button class="text-btn" data-go="collection">Collection</button></div><p class="saved-note">Your forged cards and evidence stay in your collection. ${!r.opponent_online?'Your rival is disconnected; they can return to this room.':''}</p></div>${logHTML()}`;
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
  $('#identity').textContent=state.profile?.nickname||'GUEST SIGNAL';
  document.querySelectorAll('nav [data-go]').forEach(b=>b.classList.toggle('active',b.dataset.go===state.route));
}
async function routeChanged() {
  const [route,id]=location.hash.slice(1).split('/');
  state.route=['home','forge','collection','reveal','room'].includes(route)?route:'home';
  if(state.route!=='room') disconnect();
  try {
    if(state.route==='forge'&&state.profile&&!state.attempt){render();state.attempt=await api('/forge/start',{generate:false,known_good:params.get('case')==='demo'});}
    if(state.route==='collection'&&state.token) state.profile=await api('/me');
    if(state.route==='reveal') {state.card=state.profile?.cards.find(c=>c.id===id)||state.card;if(!state.card){nav('collection');return;}}
    if(state.route==='forge'&&state.attempt)state.reason=sessionStorage.getItem(`${key}-draft-${state.attempt.id}`)||state.attempt.response||'';
    render();
    if(state.route==='room') {const code=(id||sessionStorage.getItem(`${key}-room`)||'').toUpperCase();if(!code||!state.token){nav('collection');return;}connect(code);}
    window.scrollTo(0,0);
  } catch(e){toast(e.message,true);$('#main').innerHTML=`<div class="error-box">${esc(e.message)}<div class="back-row"><button class="btn secondary" data-go="home">Return home</button></div></div>`;}
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
    try{await createIdentity(name);state.attempt=await api('/forge/start',{generate:false,known_good:params.get('case')==='demo'});nav('forge');}catch(e){toast(e.message,true);}finally{state.busy=false;render();}
  }else if(id==='forge-form'){
    state.busy=true;render();
    try{const result=await api('/forge',{attempt:state.attempt.id,response:state.reason.trim()});
      if(result.card){state.card=result.card;state.profile=await api('/me');sessionStorage.removeItem(`${key}-draft-${state.attempt.id}`);state.attempt=null;state.reason='';state.openEvidence.clear();nav(`reveal/${result.card.id}`);}
      else{state.attempt={...state.attempt,assessment:result.assessment,can_retry:result.can_retry,retry_count:result.retry_count};toast(result.can_retry?'Forge unstable. Refine your call for one quick retry.':'This forge is closed. Open a new case.');}
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
  }catch(e){$('#main').innerHTML=`<section class="error-box"><h2>The terminal is offline.</h2><p>${esc(e.message)}</p><button class="btn primary" onclick="location.reload()">Reconnect</button></section>`;}
}
boot();
