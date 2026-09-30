// Pure template smoke test. Does not launch or control a browser, or verify layout.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const context = vm.createContext({
  URLSearchParams, console, fixture,
  localStorage: {getItem:()=>null}, sessionStorage: {getItem:()=>null},
  location: {search:'', hash:'', pathname:'/'},
  document: {addEventListener:()=>{}, querySelector:()=>null},
  window: {addEventListener:()=>{}},
});
const source = fs.readFileSync('static/app.js','utf8').replace(/boot\(\);\s*$/, '');
vm.runInContext(source,context);
vm.runInContext(`
  state.config=fixture.config;state.profile=fixture.profile;state.attempt=fixture.attempt;
  state.card=fixture.card;state.room=fixture.room;state.connected=true;
`,context);
for(const screen of ['home','forge','reveal','collection','duel']){
  const html=vm.runInContext(`state.route='${screen==='duel'?'room':screen}';${screen}HTML()`,context);
  assert(!html.includes('[object Object]'),screen);
  assert(!html.includes('undefined'),screen);
  assert(html.length>200,screen);
}
let html=vm.runInContext(`state.attempt.assessment={verdict:'fail',feedback:'Add a case detail and an action.',notice:'Approximate local analysis.'};state.attempt.can_retry=true;forgeHTML()`,context);
assert(html.includes('Make the decision more specific'));
html=vm.runInContext(`state.playCard=fixture.card.id;state.front='Evidence';state.battleText='<script>bad()</script>';duelHTML()`,context);
assert(html.includes('battle-response'));
assert(!html.includes('<script>bad()'));
html=vm.runInContext(`state.room.locked=true;state.room.evaluating=true;state.room.own_play={card:fixture.card,front:'Evidence',response:'A sealed written move.'};duelHTML()`,context);
assert(html.includes('Resolving move'));
console.log('PASS: landing, forge, unstable retry, reveal, collection, duel, pending evaluation, and escaped player text render without template errors. Layout not tested.');
