import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url), compiled = await build({
  stdin: { contents: `export * from './audio/preferences'; export * from './audio/SoundEvents';
    export * from './audio/AudioManager'; export * from './audio/AudioProvider';
    export {default as AudioSettings,AudioButton} from './audio/AudioSettings';`,
    resolveDir: fileURLToPath(new URL('../src/', import.meta.url)), loader: 'tsx' },
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime'], loader: { '.css': 'empty' },
});
const module = { exports: {} };
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(require,module,module.exports);
const {readAudioPreferences,writeAudioPreferences,DEFAULT_AUDIO,AUDIO_STORAGE_KEY,collectSoundEvents,eventSound,
  AudioManager,MAX_SOUND_VOICES,AudioProvider,AudioSettings} = module.exports;
const memory = value => ({value, getItem(key){assert.equal(key,AUDIO_STORAGE_KEY);return this.value;},
  setItem(key,value){assert.equal(key,AUDIO_STORAGE_KEY);this.value=value;}});
const event = (type,id=1,extra={}) => ({type,id,tick:1,at_ms:1,actor_pid:0,...extra});
function frame(extra={}) { return {key:'ROOM:1',tick:0,pid:0,live:true,
  state:{turn:0,phase:'main',you_pid:0,game_events:[],trade_offers:[],...extra.state},...extra}; }
const baseline = extra => collectSoundEvents(null,frame(extra)).cursor;
const cues = result => result.sounds.map(s=>s.cue);

test('audio defaults are quiet and preferences round-trip only browser-local values',()=>{
  const store=memory();assert.deepEqual(readAudioPreferences(store),DEFAULT_AUDIO);
  const p={master:.8,sfx:.3,music:.12,muted:true};writeAudioPreferences(p,store);
  assert.deepEqual(readAudioPreferences(store),p);
  assert.deepEqual(Object.keys(JSON.parse(store.value)).sort(),['master','music','muted','sfx','version']);
});
test('corrupt/unsupported/denied storage is optional; volumes are finite, clamped and never coerced',()=>{
  for(const value of ['broken','null','[]','{"version":2,"master":1}']) assert.deepEqual(readAudioPreferences(memory(value)),DEFAULT_AUDIO);
  const denied={getItem(){throw Error('denied');},setItem(){throw Error('denied');}};
  assert.deepEqual(readAudioPreferences(denied),DEFAULT_AUDIO);assert.doesNotThrow(()=>writeAudioPreferences(DEFAULT_AUDIO,denied));
  assert.deepEqual(readAudioPreferences(memory(JSON.stringify({version:1,master:9,sfx:-1,music:'1',muted:'yes'}))),
    {master:1,sfx:0,music:.12,muted:false});
});
test('existing committed command kinds map to distinct building/card/movement cues, never debug/intents/ACKs',()=>{
  const pairs={place_road:'road',place_settlement:'settlement',upgrade_city:'city',build_ship:'ship',move_ship:'ship_move',
    buy_dev:'dev_buy',play_dev:'dev_play',trade_bank:'bank_trade',move_robber:'robber',move_pirate:'pirate',theft:'theft'};
  for(const [kind,cue] of Object.entries(pairs)) assert.equal(eventSound(event(kind)),cue);
  for(const kind of ['debug','noop','cmd_ack','error','hover','place_ship','trade_offer_accept']) assert.equal(eventSound(event(kind)),undefined);
});
test('initial hydration including a finished match produces no historical effects',()=>{
  const f=frame({state:{turn:0,phase:'main',game_over:true,winner_pid:0,game_events:[event('place_road'),event('theft',2)]}});
  assert.deepEqual(cues(collectSoundEvents(null,f)),[]);
  assert.deepEqual(cues(collectSoundEvents(null,{...f,state:{...f.state,game_over:false}})),[]);
});
test('a known live lobby start or rematch gets one start cue; restored/disconnected start does not',()=>{
  const first=collectSoundEvents(null,frame({freshStart:true}));assert.deepEqual(cues(first),['game_start']);
  assert.deepEqual(cues(collectSoundEvents(first.cursor,frame({freshStart:true}))),[]);
  assert.deepEqual(cues(collectSoundEvents(first.cursor,frame({key:'ROOM:2'}))),['game_start']);
  assert.deepEqual(cues(collectSoundEvents({...first.cursor,live:false},frame({key:'ROOM:2'}))),[]);
  assert.deepEqual(cues(collectSoundEvents(null,frame({freshStart:true,live:false}))),[]);
});
test('confirmed builds play once; unchanged/rejected snapshots, repeated feed/ACK and rerenders play nothing',()=>{
  const before=baseline(), after=frame({tick:1,state:{turn:0,phase:'main',game_events:[event('place_road')]}});
  assert.deepEqual(cues(collectSoundEvents(before,frame())),[]);
  const accepted=collectSoundEvents(before,after);assert.deepEqual(cues(accepted),['road']);
  assert.deepEqual(cues(collectSoundEvents(accepted.cursor,{...after,state:{...after.state,players:[{name:'changed UI'}]}})),[]);
  assert.deepEqual(cues(collectSoundEvents(accepted.cursor,{...after,state:{...after.state,game_events:[]}})),[]);
  assert.deepEqual(cues(collectSoundEvents(accepted.cursor,{...after,tick:0})),[]);
});
test('reconnect consumes the restored high-water mark and allows only later live effects',()=>{
  let cursor=baseline();cursor=collectSoundEvents(cursor,frame({live:false})).cursor;
  const restored=frame({tick:8,state:{turn:1,phase:'main',game_events:[event('place_road',6),event('upgrade_city',8)]}});
  const reconnect=collectSoundEvents(cursor,restored);assert.deepEqual(cues(reconnect),[]);
  const later=collectSoundEvents(reconnect.cursor,{...restored,tick:9,state:{...restored.state,game_events:[...restored.state.game_events,event('place_settlement',9)]}});
  assert.deepEqual(cues(later),['settlement']);
});
test('hidden-tab/foreground and pid ownership changes establish a baseline without playback',()=>{
  const hidden=collectSoundEvents(baseline(),frame({live:false,tick:4,state:{turn:1,phase:'main',game_events:[event('move_robber',4)]}}));
  assert.deepEqual(cues(hidden),[]);
  assert.deepEqual(cues(collectSoundEvents(hidden.cursor,frame({tick:5,state:{turn:0,phase:'main',game_events:[event('move_pirate',5)]}}))),[]);
  assert.deepEqual(cues(collectSoundEvents(baseline(),frame({pid:1,tick:2,state:{turn:1,phase:'main',game_events:[event('buy_dev',2)]}}))),[]);
});
test('dice sounds follow authoritative roll identity and remaining visual settle time; reduced motion skips rolling',()=>{
  const f=frame({tick:1,diceElapsed:120,state:{turn:0,phase:'main',game_events:[event('roll')]}});
  const sounds=collectSoundEvents(baseline(),f).sounds;
  assert.deepEqual(sounds.map(s=>[s.cue,s.delay]),[['dice_roll',0],['dice_land',780]]);
  assert.deepEqual(cues(collectSoundEvents(baseline(),{...f,reduced:true})),['dice_land']);
  assert.equal(collectSoundEvents(baseline(),{...f,diceElapsed:1200}).sounds[1].delay,0);
});
test('many production recipients produce one table cue and one own-hand cue per committed tick',()=>{
  const events=[event('roll'),...Array.from({length:5},(_,pid)=>event('production',pid+2,{player_pid:pid,quantity:5}))];
  const result=collectSoundEvents(baseline(),frame({tick:1,state:{turn:0,phase:'main',game_events:events}}));
  assert.deepEqual(cues(result),['dice_roll','dice_land','production','hand']);
  assert.deepEqual(cues(collectSoundEvents(result.cursor,frame({tick:1,state:{turn:0,phase:'main',game_events:events}}))),[]);
  const other=collectSoundEvents(baseline({pid:9}),frame({pid:9,tick:1,state:{turn:0,phase:'main',game_events:events}}));
  assert(!cues(other).includes('hand'));
});
test('private resource/card identities are not inspected and cannot change an observer theft sound',()=>{
  const theft=event('theft',1,{victim_pid:1});
  for(const name of ['resource','resources','card'])Object.defineProperty(theft,name,{get(){throw Error('private field read');}});
  for(const pid of [0,1,2])assert.deepEqual(cues(collectSoundEvents(baseline({pid}),frame({pid,tick:1,state:{turn:0,phase:'main',game_events:[theft]}}))),['theft']);
  assert.equal(eventSound({...event('buy_dev'),card:'victory_point'}),'dev_buy');
});
test('addressed incoming offers notify once; accept/cancel use actual status and skip unrelated targeted offers',()=>{
  const offer={offer_id:1,from_pid:1,to_pid:0,status:'active',give:{wood:1},get:{brick:1}},before=baseline();
  const next=frame({tick:1,state:{turn:0,phase:'main',trade_offers:[offer],game_events:[event('trade_offer_create')]}});
  const received=collectSoundEvents(before,next);assert.deepEqual(cues(received),['trade_offer']);
  assert.deepEqual(cues(collectSoundEvents(received.cursor,next)),[]);
  for(const [status,cue] of [['accepted','trade_accept'],['declined','trade_cancel'],['canceled','trade_cancel']]){
    const f={...next,tick:2,state:{...next.state,trade_offers:[{...offer,status}],game_events:[event('trade_offer_accept',2)]}};
    assert.deepEqual(cues(collectSoundEvents(received.cursor,f)),status==='accepted'?[cue,'hand']:[cue]);
  }
  assert.deepEqual(cues(collectSoundEvents(before,{...next,state:{...next.state,trade_offers:[{...offer,to_pid:2}]}})),[]);
});
test('own bank/gold gains and confirmed dev-card resource gains get one generic hand cue, never opponents or debug grants',()=>{
  const before=baseline({state:{turn:0,phase:'main',players:[{pid:0,resource_count:3}]}});
  for(const type of ['trade_bank','choose_gold','play_dev']){
    const f=frame({tick:1,state:{turn:0,phase:'main',players:[{pid:0,resource_count:5}],game_events:[event(type)]}});
    const next=collectSoundEvents(before,f);assert.equal(cues(next).filter(c=>c==='hand').length,1);
    assert.deepEqual(cues(collectSoundEvents(next.cursor,f)),[]);
    assert(!cues(collectSoundEvents(before,{...f,state:{...f.state,game_events:[event(type,1,{actor_pid:1})]}})).includes('hand'));
  }
  assert(!cues(collectSoundEvents(before,frame({tick:1,state:{turn:0,phase:'main',players:[{pid:0,resource_count:8}],game_events:[event('debug')]}}))).includes('hand'));
});
test('a trade participant receives a hand cue even for a net card-count decrease; an uninvolved observer only hears acceptance',()=>{
  const offer={offer_id:1,from_pid:0,to_pid:null,status:'active',give:{wood:2},get:{ore:1}};
  for(const pid of [0,1,2]){
    const before=baseline({pid,state:{turn:0,phase:'main',trade_offers:[offer]}});
    const next=collectSoundEvents(before,frame({pid,tick:1,state:{turn:0,phase:'main',trade_offers:[{...offer,status:'accepted'}],game_events:[event('trade_offer_accept',1,{actor_pid:1})]}}));
    assert.deepEqual(cues(next),pid===2?['trade_accept']:['trade_accept','hand']);
  }
});
test('own turn and final result transitions play once; other turns and final hydration stay silent',()=>{
  const before=baseline({state:{phase:'main',turn:1}}), own=collectSoundEvents(before,frame({tick:1}));
  assert.deepEqual(cues(own),['turn']);assert.deepEqual(cues(collectSoundEvents(own.cursor,frame({tick:2}))),[]);
  const win=frame({tick:3,state:{turn:0,phase:'main',game_over:true,winner_pid:0}});
  const result=collectSoundEvents(own.cursor,win);assert.deepEqual(cues(result),['victory']);
  assert.deepEqual(cues(collectSoundEvents(result.cursor,win)),[]);
  assert.deepEqual(cues(collectSoundEvents(own.cursor,{...win,state:{...win.state,winner_pid:1}})),['game_over']);
});

// Lifecycle/mixing model only. Chrome acceptance separately uses actual native nodes and audible output samples.
class Param { constructor(value=1){this.value=value;this.calls=[];} }
for(const method of ['setValueAtTime','linearRampToValueAtTime','exponentialRampToValueAtTime','setTargetAtTime'])
  Param.prototype[method]=function(value,...args){this.value=value;this.calls.push([method,value,...args]);};
Param.prototype.cancelScheduledValues=function(at){this.calls.push(['cancel',at]);};
class Node {
  constructor(context,kind){this.context=context;this.kind=kind;this.gain=new Param();this.frequency=new Param();this.connections=[];this.disconnected=false;}
  connect(to){this.connections.push(to);return to;}disconnect(){this.disconnected=true;this.connections=[];}
  start(at=0){this.started=at;this.context.sources.push(this);}
  stop(at){if(at===undefined){this.stopped=true;this.onended?.();}else this.stopAt=at;}
}
class NativeModel {
  constructor(){this.nodes=[];this.sources=[];this.state='suspended';this.currentTime=0;this.destination={};this.resumes=0;this.closed=0;}
  node(kind){const node=new Node(this,kind);this.nodes.push(node);return node;}
  createGain(){return this.node('gain');}createOscillator(){return this.node('tone');}createBufferSource(){return this.node('noise');}
  createBiquadFilter(){return this.node('filter');}
  createDynamicsCompressor(){const n=this.node('limiter');for(const k of ['threshold','knee','ratio','attack','release'])n[k]=new Param();return n;}
  createBuffer(_,length){const data=new Float32Array(length);return{getChannelData:()=>data};}
  resume(){this.resumes++;if(this.reject)return Promise.reject(Error('blocked'));this.state='running';this.onstatechange?.();return Promise.resolve();}
  suspend(){this.state='suspended';this.onstatechange?.();return Promise.resolve();}
  close(){this.closed++;this.state='closed';return Promise.resolve();}
  advance(time){this.currentTime=time;for(const s of this.sources)if(!s.stopped&&s.stopAt<=time){s.stopped=true;s.onended?.();}}
}
async function unlocked(){const context=new NativeModel(),store=memory(),manager=new AudioManager(()=>context,store);
  manager.enterMatch();await manager.unlock();return{manager,context,store};}
test('context is lazy, shared across effects and contains separate master/SFX/music buses',async()=>{
  let made=0;const context=new NativeModel(),manager=new AudioManager(()=>{made++;return context;},memory());
  assert.equal(made,0);assert.equal(manager.getSnapshot().ready,'locked');manager.enterMatch();
  assert.equal(manager.play({id:'locked',cue:'road'}),false);assert.equal(made,0);
  await manager.unlock();await manager.unlock();assert.equal(made,1);
  assert.equal(manager.play({id:'first',cue:'road'}),true);assert.equal(manager.play({id:'second',cue:'city'}),true);
  const buses=context.nodes.filter(n=>n.kind==='gain').slice(0,3);assert.deepEqual(buses.map(n=>n.gain.value),[.7,.65,.12]);
  manager.dispose();assert.equal(context.closed,1);
});
test('mute/zero SFX stop scheduled effects; unmuting never replays a consumed cue',async()=>{
  const {manager,context}=await unlocked();const cue={id:'queued-hand',cue:'hand',delay:640};assert(manager.play(cue));
  manager.setPreferences({muted:true});assert(context.sources.every(s=>s.stopped));assert.equal(context.nodes[0].gain.value,0);
  assert.equal(manager.play({id:'muted',cue:'road'}),false);manager.setPreferences({muted:false});assert.equal(manager.play(cue),false);
  manager.setPreferences({sfx:0});assert.equal(manager.play({id:'zero',cue:'city'}),false);assert.equal(context.nodes[2].gain.value,.12);
  manager.dispose();
});
test('duplicate IDs and crowded equal/lower-priority effects do not play; significant cues can replace a low one',async()=>{
  const {manager,context}=await unlocked();for(let i=0;i<MAX_SOUND_VOICES;i++)assert(manager.play({id:String(i),cue:'road',priority:2}));
  assert.equal(manager.play({id:'0',cue:'road'}),false);assert.equal(manager.play({id:'crowded',cue:'road',priority:1}),false);
  assert(manager.play({id:'result',cue:'victory',priority:7}));assert(context.sources.some(s=>s.stopped));manager.dispose();
});
test('completed voices free capacity and resource cooldowns group rapid bursts',async()=>{
  const {manager,context}=await unlocked();assert(manager.play({id:'p1',cue:'production'}));assert.equal(manager.play({id:'p2',cue:'production'}),false);
  context.advance(1);assert(manager.play({id:'p3',cue:'production'}));
  context.advance(2);for(let i=0;i<MAX_SOUND_VOICES;i++)assert(manager.play({id:'r'+i,cue:'road'}));manager.dispose();
});
test('music requires explicit opt-in, does not restart for state/settings updates, and is independently controllable',async()=>{
  const {manager,context,store}=await unlocked();assert.equal(manager.getSnapshot().musicPlaying,false);
  manager.setMusic(true);await manager.unlock(true);assert(manager.getSnapshot().musicPlaying);
  const sources=context.sources.length;manager.enterMatch();manager.setPreferences({sfx:.2,music:.1});assert.equal(context.sources.length,sources);
  manager.setMusic(false);assert.equal(manager.getSnapshot().musicPlaying,false);context.advance(.1);assert(context.sources.every(s=>s.stopped));
  assert(!('musicWanted' in JSON.parse(store.value)));manager.dispose();
});
test('hidden tab cancels delayed SFX and pauses opted-in music; foreground resumes only that preference',async()=>{
  const {manager,context}=await unlocked();manager.setMusic(true);await manager.unlock(true);manager.play({id:'pending',cue:'dice_land',delay:900});
  manager.setVisible(false);assert.equal(context.state,'suspended');assert.equal(manager.getSnapshot().musicPlaying,false);
  assert(context.sources.every(s=>s.stopped));assert.equal(manager.play({id:'hidden',cue:'city'}),false);
  manager.setVisible(true);await manager.unlock(true);assert(manager.getSnapshot().musicPlaying);manager.setMusic(false);
  manager.setVisible(false);manager.setVisible(true);await manager.unlock(true);assert.equal(manager.getSnapshot().musicPlaying,false);manager.dispose();
});
test('leaving match stops playback and music intent; final disposal closes context and disconnects nodes',async()=>{
  const {manager,context}=await unlocked();manager.setMusic(true);await manager.unlock(true);manager.play({id:'road',cue:'road'});
  manager.leaveMatch();assert(context.sources.every(s=>s.stopped));assert.equal(manager.getSnapshot().musicWanted,false);
  assert.equal(manager.play({id:'outside',cue:'road'}),false);manager.dispose();manager.dispose();
  assert.equal(context.closed,1);assert(context.nodes.every(n=>n.disconnected));
});
test('rapid hide/show waits for asynchronous suspend and restores unlocked audio exactly once',async()=>{
  const {manager,context}=await unlocked();manager.setMusic(true);await manager.unlock(true);
  let finish;context.suspend=()=>new Promise(resolve=>{finish=()=>{context.state='suspended';context.onstatechange?.();resolve();};});
  manager.setVisible(false);manager.setVisible(true);finish();await Promise.resolve();await Promise.resolve();
  assert.equal(context.state,'running');assert(manager.getSnapshot().musicPlaying);assert.equal(context.resumes,2);manager.dispose();
});
test('StrictMode lease replay preserves the context; actual provider unmount releases it once',async()=>{
  const {manager,context}=await unlocked();const first=manager.retain();first();const second=manager.retain();
  await Promise.resolve();assert.equal(context.closed,0);second();second();await Promise.resolve();assert.equal(context.closed,1);
});
test('unsupported audio/resume rejection fail silently without autoplay retry loops; explicit retry can recover',async()=>{
  let tries=0;const missing=new AudioManager(()=>{tries++;throw Error('unsupported');},memory());
  await missing.unlock();await missing.unlock();assert.equal(tries,1);assert.equal(missing.getSnapshot().ready,'unavailable');missing.dispose();
  const context=new NativeModel();context.reject=true;const manager=new AudioManager(()=>context,memory());
  await manager.unlock();await manager.unlock();assert.equal(context.resumes,1);assert.equal(manager.getSnapshot().ready,'blocked');
  context.reject=false;await manager.unlock(true);assert.equal(manager.getSnapshot().ready,'running');manager.dispose();
});
test('SFX never notify React per frame/per voice and stale unlock completion cannot resurrect disposed audio',async()=>{
  const {manager}=await unlocked();let updates=0;manager.subscribe(()=>updates++);
  manager.play({id:'test',cue:'road'});assert.equal(updates,0);manager.dispose();
  const context=new NativeModel();let resolve;context.resume=()=>new Promise(r=>{resolve=r;});
  const pending=new AudioManager(()=>context,memory());const work=pending.unlock();pending.dispose();resolve();await work;
  assert.equal(context.closed,1);assert.equal(pending.getSnapshot().musicPlaying,false);
});
test('compact settings expose labelled percentage sliders/mute/test/music controls without becoming a permanent panel',()=>{
  const html=renderToStaticMarkup(React.createElement(AudioProvider,null,React.createElement(AudioSettings,{onClose(){}})));
  for(const label of ['Master volume','Sound effects volume','Music volume','Mute all audio','Test sound','Play music'])assert(html.includes(label));
  assert(html.includes('12%'));assert(html.includes('role="dialog"'));assert(!html.includes('aria-modal="true"'));
  assert(!html.includes('spotify'));assert(!html.includes('audio src='));
});
