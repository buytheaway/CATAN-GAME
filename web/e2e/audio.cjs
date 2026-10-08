// Production dist + existing real fixture_server/WS + native Chrome Web Audio.
// Web Audio is observed, never mocked. Only static dist routing and explicit failure cases are controlled.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium}=require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18765';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(),'catan-audio-phase4');
const h=require('./game-actions.cjs'),origin=process.env.CATAN_E2E_ORIGIN,out=process.env.CATAN_E2E_OUTPUT;
const dist=path.resolve(__dirname,'../dist'),sleep=ms=>new Promise(r=>setTimeout(r,ms)),contexts=[];
const report={checks:[],commands:0,rejected:0,layouts:[],nativeAudio:[],performance:[]};

function nativeAudioObserver(){
  const Native=window.AudioContext;window.__audio={contexts:[],externalFiles:[]};
  if(!Native)return;
  window.AudioContext=new Proxy(Native,{construct(Constructor,args){
    const begin=performance.now(),context=Reflect.construct(Constructor,args);
    const a={context,sources:[],gains:[],nodes:[],resumes:[],initMs:0};window.__audio.contexts.push(a);
    for(const name of ['createGain','createOscillator','createBufferSource','createBiquadFilter','createDynamicsCompressor']){
      const original=context[name].bind(context);
      context[name]=(...args)=>{
        const node=original(...args);a.nodes.push(node);
        if(name==='createGain')a.gains.push(node);
        if(name==='createOscillator'||name==='createBufferSource'){
          const start=node.start.bind(node),stop=node.stop.bind(node);let frequency;
          if(node.frequency){const set=node.frequency.setValueAtTime.bind(node.frequency);node.frequency.setValueAtTime=(v,t)=>{frequency??=v;return set(v,t);};}
          node.start=(at=context.currentTime,...rest)=>{const entry={kind:name==='createOscillator'?'tone':'noise',
            frequency:frequency??node.frequency?.value,at,called:context.currentTime,node};a.sources.push(entry);node.__audioEntry=entry;return start(at,...rest);};
          node.stop=(at=context.currentTime)=>{if(node.__audioEntry)node.__audioEntry.stopAt=at;return stop(at);};
        }
        if(name==='createDynamicsCompressor'){
          const connect=node.connect.bind(node),analyser=context.createAnalyser();analyser.fftSize=1024;a.analyser=analyser;
          node.connect=(target,...rest)=>{if(target===context.destination){connect(analyser);analyser.connect(target);return target;}return connect(target,...rest);};
        }
        return node;
      };
    }
    const resume=context.resume.bind(context);context.resume=()=>{
      const at=performance.now();if(!a.initMs)a.initMs=at-begin;
      return resume().then(value=>{a.resumes.push(performance.now()-at);return value;});
    };
    return context;
  }});
}
async function newContext(browser,options){
  const context=await browser.newContext(options);contexts.push(context);await context.addInitScript(nativeAudioObserver);
  await context.grantPermissions(['local-network-access'],{origin});
  await context.route(origin+'/**',async route=>{
    const p=new URL(route.request().url()).pathname;
    if(p==='/'||p.startsWith('/assets/')||p.startsWith('/models/')){
      const file=path.join(dist,p==='/'?'index.html':p);
      return route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.html')?'text/html':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'model/gltf-binary'});
    }
    if(/\.(mp3|wav|ogg|m4a|aac|flac)$/.test(p))throw Error('Unexpected audio asset download '+p);
    return route.continue();
  });return context;
}
async function audio(c){return c.page.evaluate(()=>{
  const a=window.__audio.contexts[0];return{contexts:window.__audio.contexts.length,state:a?.context.state,
    sources:a?.sources.length??0,initMs:a?.initMs,resumes:a?.resumes,gains:a?.gains.slice(0,3).map(g=>g.gain.value),
    starts:a?.sources.map(s=>({kind:s.kind,at:s.at,frequency:s.frequency,stopped:s.stopAt!=null&&s.stopAt<=a.context.currentTime}))??[]};
});}
async function peak(c,ms=180){return c.page.evaluate(async duration=>{
  const a=window.__audio.contexts[0];if(!a?.analyser)return 0;
  const values=new Float32Array(a.analyser.fftSize),end=performance.now()+duration;let peak=0;
  while(performance.now()<end){a.analyser.getFloatTimeDomainData(values);for(const v of values)peak=Math.max(peak,Math.abs(v));await new Promise(r=>setTimeout(r,12));}
  return peak;
},ms);}
async function quiet(cs){await sleep(1900);for(const c of cs){const f=await audio(c);assert.equal(f.contexts,1);assert.equal(f.state,'running');}}
async function close(cs){for(const c of cs){
  const f=await audio(c);report.nativeAudio.push({initMs:f.initMs,resumeMs:f.resumes?.[0],contexts:f.contexts});
  assert.deepEqual(c.jsErrors,[]);assert.deepEqual(c.console.filter(x=>!x.includes('status of 503')),[]);
  await c.context.close();
}}
async function action(cs,c,run,label,{silent=false,rejected=false}={}){
  const before=await audio(c);await h.action(cs,c,run,label,rejected);report.commands++;if(rejected)report.rejected++;
  await sleep(50);const after=await audio(c);
  if(silent||rejected)assert.equal(after.sources,before.sources,label+' must not start an effect');
  else assert(after.sources>before.sources,label+' must schedule native audio after confirmed state');
  return {before,after};
}
async function settings(c){await c.page.getByRole('button',{name:'Audio settings',exact:true}).click();const p=c.page.getByRole('dialog',{name:'Audio settings',exact:true});await p.waitFor();return p;}
async function volume(p,name,value){const input=p.getByRole('slider',{name,exact:true});await input.focus();
  await input.press(value>50?'End':'Home');for(let i=0;i<(value>50?100-value:value);i++)await input.press(value>50?'ArrowLeft':'ArrowRight');
  assert.equal(await input.inputValue(),String(value));}
async function shot(c,name){await c.page.screenshot({path:path.join(out,name+'.png')});}

async function natural(browser){
  const cs=await h.room(browser,'direct',2,true),a=cs[0];await quiet(cs);
  while(a.match.state.phase==='setup'){
    const c=cs[a.match.state.turn],settlement=c.match.state.setup_need==='settlement';await h.open3d(c);
    await action(cs,c,()=>h.clickTarget(c,settlement?'vertex':'edge',settlement?c.match.state.legal.settlements[0]:c.match.state.legal.roads[0]),'natural setup '+(settlement?'settlement':'road'));
  }
  await quiet(cs);const roll=await action(cs,a,()=>a.page.getByRole('button',{name:'Roll',exact:true}).click(),'natural Roll');
  assert(roll.after.starts.slice(roll.before.sources).some(s=>s.at-roll.after.starts[roll.before.sources].at>.7),'native landing is delayed to dice settle');
  assert((await peak(a))>0.0001,'native SFX graph produces nonzero output');await quiet(cs);
  const other=await audio(cs[1]);await action(cs,a,()=>a.page.getByRole('button',{name:'End Turn',exact:true}).click(),'turn passes to other player',{silent:true});
  assert((await audio(cs[1])).sources>other.sources,'new owner receives the turn cue');
  report.checks.push('Natural Base: gesture unlock, game start, first/second setup settlement/roads, actual Roll/landing/output and turn transition');await close(cs);
}
async function builds(browser){
  const cs=await h.room(browser,'direct'),a=cs[0];await h.open3d(a);await quiet(cs);
  for(const [kind,field,type] of [['City','cities','vertex'],['Road','roads','edge']]){
    const target=a.match.state.legal[field][0],before=await audio(a);assert(target!==undefined);
    await a.page.getByRole('button',{name:kind,exact:true}).click();assert.equal((await audio(a)).sources,before.sources,'selecting build is silent');
    await action(cs,a,()=>h.clickTarget(a,type,target),'paid '+kind);
  }
  for(let i=0;!a.match.state.legal.settlements.length&&i<6;i++){
    const edge=a.match.state.legal.roads[0];assert(edge);const button=a.page.getByRole('button',{name:'Road',exact:true});
    if(await button.getAttribute('aria-pressed')!=='true')await button.click();await action(cs,a,()=>h.clickTarget(a,'edge',edge),'extend road');
  }
  const v=a.match.state.legal.settlements[0];assert(v!==undefined);await a.page.getByRole('button',{name:'Settlement',exact:true}).click();
  await action(cs,a,()=>h.clickTarget(a,'vertex',v),'paid settlement');await quiet(cs);
  await h.invalidNext(a,{type:'place_road',eid:[-999,-998]});
  await action(cs,a,()=>a.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'rejected coordinate',{rejected:true});
  const count=await audio(a),request=a.sent.at(-1),duplicates=a.acks.length;
  await a.page.evaluate(message=>window.__sockets.at(-1).send(JSON.stringify(message)),request);
  await h.wait(()=>a.acks.length>duplicates,'real duplicate ACK');assert(a.acks.at(-1).duplicate);await sleep(200);
  assert.equal((await audio(a)).sources,count.sources,'duplicate ACK never sounds');
  await a.page.getByRole('button',{name:'2D',exact:true}).click();await a.page.getByRole('button',{name:'3D',exact:true}).click();await sleep(400);
  assert.equal((await audio(a)).sources,count.sources,'renderer toggle never replays sounds');
  report.checks.push('Paid GLB Road/Settlement/City, silent selection/rejection/duplicate ACK and 2D/3D switching');await close(cs);
}
async function trades(browser){
  const cs=await h.room(browser,'bank4'),[a,b]=cs;await quiet(cs);
  const draft=async(bank=false)=>{
    await a.page.locator('.resource-hand button[data-resource="wood"]').click();
    const panel=a.page.getByRole('dialog',{name:'Trade tray',exact:true});await panel.waitFor();
    await panel.getByRole('button',{name:'Want ore',exact:true}).click();
    if(bank)for(let i=0;i<3;i++)await a.page.locator('.resource-hand button[data-resource="wood"]').click();return panel;
  };
  let panel=await draft();const bBefore=await audio(b);
  await action(cs,a,()=>panel.getByRole('button',{name:'Offer to Players',exact:true}).click(),'offer sender',{silent:true});
  assert((await audio(b)).sources>bBefore.sources,'recipient offer notification');
  const incoming=b.page.getByRole('dialog',{name:'Trade offers',exact:true});await incoming.waitFor();
  await action(cs,b,()=>incoming.getByRole('button',{name:'Accept',exact:true}).click(),'player trade accepted');
  panel=await draft();await action(cs,a,()=>panel.getByRole('button',{name:'Offer to Players',exact:true}).click(),'second offer sender',{silent:true});
  await action(cs,b,()=>incoming.getByRole('button',{name:'Reject',exact:true}).click(),'player trade declined');
  panel=await draft();await action(cs,a,()=>panel.getByRole('button',{name:'Offer to Players',exact:true}).click(),'third offer sender',{silent:true});
  await action(cs,a,()=>a.page.getByRole('button',{name:'Cancel offer',exact:true}).click(),'offer canceled');
  // A separate funded room preserves enough wood for the real 4:1 bank exchange.
  report.checks.push('Real incoming offer, accepted/declined/canceled status sounds without sender/intent duplication');await close(cs);
  const bank=await h.room(browser,'bank4'),c=bank[0];await quiet(bank);
  await c.page.locator('.resource-hand button[data-resource="wood"]').click();
  const bankPanel=c.page.getByRole('dialog',{name:'Trade tray',exact:true});await bankPanel.getByRole('button',{name:'Want ore',exact:true}).click();
  for(let i=0;i<3;i++)await c.page.locator('.resource-hand button[data-resource="wood"]').click();
  await action(bank,c,()=>bankPanel.getByRole('button',{name:'Bank',exact:true}).click(),'bank trade');
  report.checks.push('Actual bank trade SFX');await close(bank);
}
async function production(browser){
  const cs=await h.room(browser,'production',2,false,'base_standard',{testMode:true}),a=cs[0];await h.open3d(a);await quiet(cs);
  const s=a.match.state,tile=s.tiles.findIndex((t,i)=>i!==s.robber_tile&&t.number&&!['sea','gold','desert'].includes(t.terrain)&&
    Object.entries(s.occupied_v).some(([v,p])=>p[0]===0&&s.vertex_adj_hexes[v].includes(i)));
  assert(tile>=0);const total=s.tiles[tile].number;
  await a.page.getByRole('button',{name:'Test Tools',exact:true}).click();const panel=a.page.getByRole('dialog',{name:'Test Tools',exact:true});
  await action(cs,a,()=>panel.getByRole('button',{name:'Force turn',exact:true}).click(),'test force turn',{silent:true});
  await panel.getByLabel('Next die 1',{exact:true}).selectOption(String(Math.max(1,total-6)));
  await panel.getByLabel('Next die 2',{exact:true}).selectOption(String(Math.min(6,total-1)));
  await action(cs,a,()=>panel.getByRole('button',{name:'Set next dice',exact:true}).click(),'test dice selection',{silent:true});
  await panel.getByRole('button',{name:'Close Test Tools',exact:true}).click();
  const r=await action(cs,a,()=>a.page.getByRole('button',{name:'Roll',exact:true}).click(),'authoritative production roll');
  const events=a.match.state.game_events.filter(e=>e.type==='production');assert(events.some(e=>e.player_pid===0));h.privacy(cs);
  const times=r.after.starts.slice(r.before.sources).map(s=>s.at),start=Math.min(...times);
  assert(times.some(t=>t-start>.85&&t-start<1.0));assert(times.some(t=>t-start>1.45));
  report.checks.push('Host Test Mode same-player force-turn/queued dice are silent; real dice settle, grouped production/own hand and personalized observer feed');await close(cs);
}
async function cardsAndTheft(browser){
  const buy=await h.room(browser,'buy'),a=buy[0];await quiet(buy);
  await action(buy,a,()=>a.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'development card purchase');
  await quiet(buy);await h.invalidNext(a,{type:'play_dev',card:'knight'});
  await action(buy,a,()=>a.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'new-card rejection',{rejected:true});await close(buy);
  const cs=await h.room(browser,'knight',3),c=cs[0];for(const p of cs)await h.open3d(p);await quiet(cs);
  await action(cs,c,()=>c.page.locator('.dev-mini-card').filter({hasText:'Knight'}).click(),'development card played');await quiet(cs);
  const l=c.match.state.legal,tile=l.robber_tiles.find(t=>l.robber_victims[t]?.length);assert(tile!==undefined);
  const before=await Promise.all(cs.map(audio));
  if(l.robber_victims[tile].length>1){await h.clickTarget(c,'tile',tile);
    await action(cs,c,()=>c.page.getByRole('dialog',{name:'Choose player'}).getByRole('button',{name:c.match.state.players[l.robber_victims[tile][0]].name,exact:true}).click(),'robber theft');
  }else await action(cs,c,()=>h.clickTarget(c,'tile',tile),'robber theft');
  const theft=c.match.state.game_events.findLast(e=>e.type==='theft');assert(theft?.resource);h.privacy(cs);
  const profiles=await Promise.all(cs.map(async(p,i)=>(await audio(p)).starts.slice(before[i].sources).map(s=>[s.kind,s.frequency])));
  assert.deepEqual(profiles[0],profiles[1]);assert.deepEqual(profiles[0],profiles[2]);
  report.checks.push('Purchase/play card, rejected fresh card, actual robber/theft with identical native source profiles for thief/victim/observer');await close(cs);
}
async function gold(browser){
  const cs=await h.room(browser,'gold',2,false,'seafarers_gold_haven'),a=cs[0];await h.open3d(a);await quiet(cs);
  const ship=a.match.state.legal.ships[0];assert(ship);await a.page.getByRole('button',{name:'Ship',exact:true}).click();
  await action(cs,a,()=>h.clickTarget(a,'edge',ship),'ship construction');
  await a.page.getByRole('button',{name:'Move Ship',exact:true}).click();const l=a.match.state.legal,source=l.move_ship.sources[0];assert(source);
  const destination=l.move_ship.targets[[...source].sort((a,b)=>a-b).join(',')][0];await h.clickTarget(a,'edge',source);
  await action(cs,a,()=>h.clickTarget(a,'edge',destination),'ship movement');
  await action(cs,a,()=>a.page.locator('.dev-mini-card').filter({hasText:'Knight'}).click(),'Gold Knight');
  await a.page.getByRole('button',{name:'Pirate',exact:true}).click();const t=a.match.state.legal.pirate_tiles.find(t=>!a.match.state.legal.pirate_victims[t]?.length);assert(t!==undefined);
  await action(cs,a,()=>h.clickTarget(a,'tile',t),'pirate movement');
  report.checks.push('Gold Haven actual ship construction/move and pirate movement audio, existing Sea/Gold visuals');await close(cs);
}
async function preferences(browser){
  const cs=await h.room(browser,'direct'),a=cs[0];await quiet(cs);let panel=await settings(a);
  await a.page.setViewportSize({width:1920,height:1080});await shot(a,'audio-settings');
  await volume(panel,'Master volume',80);await volume(panel,'Sound effects volume',45);await volume(panel,'Music volume',14);
  await panel.getByRole('button',{name:'Test sound',exact:true}).click();assert((await peak(a))>.0001);await quiet(cs);
  await panel.getByRole('button',{name:'Play music',exact:true}).click();await sleep(1800);
  assert((await peak(a))>.0001,'actual optional ambient produces native output');const playing=await audio(a);
  assert(Math.abs(playing.gains[0]-.8)<.002&&Math.abs(playing.gains[1]-.45)<.002&&Math.abs(playing.gains[2]-.14)<.002);
  await shot(a,'audio-music-playing');
  await panel.getByRole('button',{name:'Close Audio settings',exact:true}).click();
  const tokens=a.tokens.length;await a.page.evaluate(()=>window.__sockets.at(-1).close());await h.wait(()=>a.tokens.length>tokens,'verified reconnect token');
  await a.page.getByText('Online',{exact:true}).waitFor();await sleep(350);
  assert.equal((await audio(a)).sources,playing.sources,'reconnect never replays or restarts music');
  panel=await settings(a);await panel.getByLabel('Mute all audio',{exact:true}).check();await sleep(150);
  assert.equal(await peak(a),0);await shot(a,'audio-muted');
  assert(await panel.getByRole('button',{name:'Pause music',exact:true}).isEnabled());await panel.getByRole('button',{name:'Pause music',exact:true}).click();
  await a.page.reload({waitUntil:'networkidle'});await a.page.locator('.game-shell').waitFor();
  assert.equal((await audio(a)).contexts,0,'refresh creates no context before a gesture');
  panel=await settings(a);for(const [name,v]of [['Master volume',80],['Sound effects volume',45],['Music volume',14]])assert.equal(await panel.getByRole('slider',{name,exact:true}).inputValue(),String(v));
  assert(await panel.getByLabel('Mute all audio',{exact:true}).isChecked());assert.equal((await audio(a)).sources,0);
  await panel.getByLabel('Mute all audio',{exact:true}).uncheck();await panel.getByRole('button',{name:'Play music',exact:true}).click();await sleep(1800);
  const count=await audio(a);await panel.getByRole('button',{name:'Close Audio settings',exact:true}).click();
  await a.page.evaluate(()=>{window.__audioHidden=true;Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__audioHidden?'hidden':'visible'});document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal((await audio(a)).state,'suspended');assert((await audio(a)).starts.every(s=>s.stopped),'hidden tab stops queued/ambient nodes');
  await action(cs,a,()=>a.page.getByRole('button',{name:'End Turn',exact:true}).click(),'hidden tab consumes live transition',{silent:true});
  await a.page.evaluate(()=>{window.__audioHidden=false;document.dispatchEvent(new Event('visibilitychange'));});await sleep(1800);
  const resumed=await audio(a);assert.equal(resumed.sources,count.sources+8,'only opted-in ambient nodes resume, no historical SFX');
  await a.page.evaluate(()=>{window.__audioHidden=true;document.dispatchEvent(new Event('visibilitychange'));
    window.__audioHidden=false;document.dispatchEvent(new Event('visibilitychange'));});
  await a.page.waitForFunction(()=>window.__audio.contexts[0].context.state==='running');await sleep(1200);
  assert.equal((await audio(a)).sources,resumed.sources+8,'rapid hide/show resumes exactly one ambient, no lost context or replay');
  for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1280,height:720}]){
    await a.page.setViewportSize(size);panel=await settings(a);await sleep(120);
    const layout=await a.page.evaluate(()=>{
      const p=document.querySelector('#audio-settings').getBoundingClientRect(),chat=document.querySelector('.sidebar-chat').getBoundingClientRect();
      return{width:innerWidth,height:innerHeight,right:p.right,bottom:p.bottom,left:p.left,chatLeft:chat.left,overflow:document.documentElement.scrollWidth>innerWidth};
    });assert(!layout.overflow);assert(layout.right<=layout.chatLeft+1&&layout.bottom<=layout.height);report.layouts.push({size,...layout});
    assert(await a.page.getByLabel('Chat message',{exact:true}).isVisible());await shot(a,'audio-settings-'+size.width);
    await a.page.keyboard.press('Escape');assert.equal(await panel.count(),0);assert(await a.page.getByRole('button',{name:'Audio settings',exact:true}).evaluate(n=>n===document.activeElement));
  }
  report.checks.push('Native Test sound/ambient, independent volumes/mute/Pause while muted, refresh persistence, reconnect continuity, controlled hidden-tab policy, keyboard/focus and 1920/1440/1280 screenshots');await close(cs);
}
async function result(browser){
  const cs=await h.room(browser,'results'),a=cs[0];await quiet(cs);let panel=await settings(a);
  await panel.getByRole('button',{name:'Play music',exact:true}).click();await sleep(1700);await panel.getByRole('button',{name:'Close Audio settings',exact:true}).click();
  await action(cs,a,()=>a.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'winning purchase/victory');
  for(const c of cs)await c.page.getByRole('dialog',{name:'Match results',exact:true}).waitFor();
  const music=await audio(a);await sleep(1700);const old=a.match.match_id;
  await a.page.getByRole('button',{name:'Rematch',exact:true}).click();await h.wait(()=>cs.every(c=>c.match.match_id===old+1),'rematch');await sleep(350);
  assert.equal((await audio(a)).sources,music.sources+3,'one fresh-start chord, stable ambient and no construction history');
  report.checks.push('Actual victory/opponent game-over, fresh rematch cue and stable opted-in ambient');await close(cs);
  const exit=await h.room(browser,'results'),c=exit[0];await quiet(exit);
  await action(exit,c,()=>c.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'second result');
  await c.page.getByRole('button',{name:'Back to Lobby',exact:true}).click();await c.page.locator('.app-shell').waitFor();
  const f=await audio(c);assert.equal(f.state,'suspended');assert(f.starts.every(s=>s.stopped));assert.deepEqual(c.jsErrors,[]);
  report.checks.push('Actual GamePage unmount/Home navigation stops voices/context without browser errors');await close(exit.filter(x=>x!==c));await c.context.close();
}
async function boot(browser){
  const context=await browser.newContext({viewport:{width:1280,height:720}}),page=await context.newPage();
  await page.goto(origin,{waitUntil:'networkidle'});assert.equal(await page.evaluate(()=>window.__audio.contexts.length),0);
  await page.getByLabel('Name',{exact:true}).click();await page.waitForFunction(()=>window.__audio.contexts[0]?.context.state==='running');
  assert.equal(await page.evaluate(()=>window.__audio.contexts[0].sources.length),0,'unlock on Home creates no surprising sound or music');
  report.checks.push('Initial Home creates no audio context; trusted first gesture unlocks one silent native context');await context.close();
}
async function unavailable(browser){
  const silent={async newContext(options){const context=await browser.newContext(options);
    await context.addInitScript(()=>{window.AudioContext=undefined;window.webkitAudioContext=undefined;});return context;}};
  const cs=await h.room(silent,'direct'),a=cs[0];await h.open3d(a);const panel=await settings(a);
  assert(await panel.getByText('Audio is unavailable in this browser. You can keep playing.',{exact:true}).isVisible());
  assert(await panel.getByRole('button',{name:'Test sound',exact:true}).isDisabled());await panel.getByRole('button',{name:'Close Audio settings',exact:true}).click();
  await a.page.getByRole('button',{name:'Road',exact:true}).click();await action(cs,a,()=>h.clickTarget(a,'edge',a.match.state.legal.roads[0]),'road with audio unavailable',{silent:true});
  report.checks.push('Controlled unavailable AudioContext: clear settings explanation, silent fallback and actual gameplay still usable; no audio files required');await close(cs);
}
async function main(){
  await fs.mkdir(out,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
  const wrapped={newContext:options=>newContext(browser,options)};
  try{for(const check of [boot,natural,builds,trades,production,cardsAndTheft,gold,preferences,result,unavailable]){console.log('Checking '+check.name);await check(wrapped);}}
  catch(error){for(const context of contexts){for(const page of context.pages())if(!page.isClosed())await page.screenshot({path:path.join(out,'failure-'+contexts.indexOf(context)+'.png')}).catch(()=>{});}
    report.error=String(error);throw error;
  }finally{await fs.writeFile(path.join(out,'verification.json'),JSON.stringify(report,null,2));await browser.close();}
  console.log(JSON.stringify(report));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
