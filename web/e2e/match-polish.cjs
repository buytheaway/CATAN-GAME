// Production dist + real existing fixture server/WS. Playwright is an external test tool.
// Start fixture_server separately with CATAN_ENABLE_TEST_TOOLS=1 (or =0 for the OFF pass).
// CATAN_E2E_ORIGIN selects that isolated server; no normal Docker container is changed.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18765';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-product-polish-phase-2');
const h = require('./game-actions.cjs');
const origin = process.env.CATAN_E2E_ORIGIN;
const output = process.env.CATAN_E2E_OUTPUT;
const off = process.env.CATAN_TEST_MODE_CHECK === 'off';
const dist = path.resolve(__dirname, '../dist');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { mode: off ? 'off' : 'on', checks: [], layouts: [], performance: [], jsErrors: [] };
const contexts = [];
const edgeId = e => [...e].sort((a,b) => a-b).join(',');

async function newContext(browser, options) {
  const context = await browser.newContext(options); contexts.push(context);
  await context.grantPermissions(['local-network-access'], {origin});
  await context.route(origin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/' || pathname.startsWith('/assets/') || pathname.startsWith('/models/')) {
      const file = path.join(dist, pathname === '/' ? 'index.html' : pathname);
      const contentType = file.endsWith('.html') ? 'text/html' : file.endsWith('.js') ? 'application/javascript'
        : file.endsWith('.css') ? 'text/css' : 'model/gltf-binary';
      await route.fulfill({body:await fs.readFile(file), contentType});
    } else await route.continue();
  });
  return context;
}
async function loaded(c) {
  await h.open3d(c);
  await c.page.waitForFunction(() => {
    let tiles = 0; window.__scene?.getState().scene.traverse(o => {if(o.userData.terrainAsset) tiles++;});
    return tiles === Number(document.querySelector('.board3d')?.dataset.tileCount);
  });
}
async function shot(c, name) { await c.page.mouse.move(1,1); await sleep(250); await c.page.screenshot({path:path.join(output,name+'.png')}); }
async function sceneFacts(c) {
  return c.page.evaluate(() => {
    const {scene,gl,camera} = window.__scene.getState(); scene.updateMatrixWorld(true);
    const ports=[],boats=[],assets=[],badScenery=[]; let ocean=0;
    scene.traverse(o => {
      if(o.userData.terrainAsset)assets.push(o.userData.terrainAsset);
      if(o.userData.decorativeOcean)ocean++;
      if(o.userData.decorativeBoat)boats.push(o.position.toArray());
      if(o.userData.portReadout)ports.push({ratio:o.userData.ratio,resource:o.userData.resource});
      if(o.userData.decorativeOcean||o.userData.ambientShips||o.userData.portReadout) {
        o.traverse(child => {
          if(child.userData.tileIndex!==undefined||child.userData.targetType)badScenery.push('game target');
          if(child.isMesh) {
            const hits=[];child.raycast({ray:null},hits);if(hits.length)badScenery.push('raycast hit');
          }
        });
      }
    });
    return {ocean,boats,ports,assets,badScenery,frame:gl.info.render.frame,camera:camera.position.toArray()};
  });
}
async function layout(c,size) {
  await c.page.setViewportSize(size); await c.page.getByRole('button',{name:'Reset Camera'}).click();
  await sleep(300);
  const result=await c.page.evaluate(() => {
    const r=s=>{const x=document.querySelector(s).getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom,width:x.width,height:x.height};};
    return {size:[innerWidth,innerHeight],overflow:document.documentElement.scrollWidth>innerWidth,
      sidebar:r('.game-sidebar'),bank:r('.bank-summary'),players:r('.sidebar-players'),chat:r('.sidebar-chat'),
      input:r('#room-chat-input'),bottom:r('.game-bottom-hud'),dock:r('.action-dock'),
      sidebarOverflow:document.querySelector('.game-sidebar').scrollHeight>document.querySelector('.game-sidebar').clientHeight+1};
  });
  assert(!result.overflow,'horizontal overflow: '+JSON.stringify(result)); assert(!result.sidebarOverflow,'sidebar overflow: '+JSON.stringify(result));
  assert(result.bank.top<result.players.top&&result.players.top<result.chat.top);
  assert(result.input.top>=result.sidebar.top&&result.input.bottom<=result.sidebar.bottom,'chat input below fold');
  assert(result.bottom.top>=result.sidebar.bottom-.5,'bottom HUD overlaps sidebar');
  assert(result.dock.right<=size.width,'dock outside viewport');
  const metrics=await h.boardMetrics(c);
  assert(metrics.visible.top>=metrics.canvasBounds.top-.5&&metrics.visible.bottom<=metrics.canvasBounds.bottom+.5,'board clipped');
  assert.equal(metrics.occludedByHud,0,'HUD covers board geometry');
  report.layouts.push({map:c.match.state.map_id,...result,board:metrics.land});
}
async function performance(c) {
  return c.page.evaluate(async () => {
    const {scene,camera,gl}=window.__scene.getState(), gpu=gl.getContext(), times=[];
    for(let i=0;i<25;i++) {
      await new Promise(r=>requestAnimationFrame(r));const t=performance.now();gl.render(scene,camera);gpu.finish();
      if(i>=5)times.push(performance.now()-t);
    }
    times.sort((a,b)=>a-b);
    return {medianMs:(times[9]+times[10])/2,p90Ms:times[17],calls:gl.info.render.calls,triangles:gl.info.render.triangles};
  });
}
async function tools(c) {
  await c.page.getByRole('button',{name:'Test Tools',exact:true}).click();
  const panel=c.page.getByRole('dialog',{name:'Test Tools',exact:true});await panel.waitFor();return panel;
}
async function closeTools(panel) { await panel.getByRole('button',{name:'Close Test Tools',exact:true}).click(); }
async function testAction(cs,panel,name) { await h.action(cs,cs[0],()=>panel.getByRole('button',{name,exact:true}).click(),name); }
async function chat(cs) {
  for(const [c,text] of [[cs[0],'Ports look clear — ready when you are.'],[cs[1],'Ready. Let’s settle this island!'],[cs[0],'<b>Plain text, shared room history.</b>']]) {
    const count=cs[0].room.chat_history?.length??0;
    await c.page.getByLabel('Chat message',{exact:true}).fill(text);
    await c.page.getByRole('button',{name:'Send',exact:true}).click();
    await h.wait(()=>cs.every(x=>x.room.chat_history?.length===count+1),'chat broadcast');
  }
  for(const c of cs)assert.equal(await c.page.locator('.chat-history b').count(),0);
  const a=cs[0];await a.page.getByLabel('Chat message',{exact:true}).fill('unsent draft');
  await shot(a,'base-chat-1920');await a.page.getByRole('button',{name:'Event log',exact:true}).click();
  assert.equal(await a.page.getByLabel('Chat message',{exact:true}).inputValue(),'unsent draft');
  assert(await a.page.getByLabel('Chat message',{exact:true}).isVisible());
  assert(await a.page.locator('.gameplay-events').isVisible());await shot(a,'base-log-1920');
  await a.page.getByRole('button',{name:'Event log',exact:true}).click();
  assert.equal(await a.page.locator('.gameplay-events').count(),0);
  assert(await a.page.locator('.chat-history').isVisible());report.checks.push('permanent chat / independent log / draft / plain text');
}
async function camera(c) {
  const s=JSON.stringify(c.match.state),sent=c.sent.length;
  const before=(await sceneFacts(c)).camera,box=await c.page.locator('canvas').boundingBox();
  await c.page.mouse.move(box.x+box.width*.22,box.y+box.height*.5);await c.page.mouse.down();
  await c.page.mouse.move(box.x+box.width*.3,box.y+box.height*.55,{steps:8});await c.page.mouse.up();
  await sleep(200);assert.notDeepEqual((await sceneFacts(c)).camera,before);
  await c.page.mouse.wheel(0,-150);await sleep(200);
  await c.page.getByRole('button',{name:'Reset Camera'}).click();await sleep(250);
  await c.page.getByRole('button',{name:'2D',exact:true}).click();assert.equal(await c.page.locator('svg[height]').count(),1);
  assert.equal(await c.page.locator('canvas').count(),0);await loaded(c);
  assert.equal(c.sent.length,sent);assert.equal(JSON.stringify(c.match.state),s);
  report.checks.push('orbit / zoom / reset / 2D-3D without commands');
}
async function motion(c) {
  await c.page.mouse.move(1,1);const before=await sceneFacts(c);await sleep(650);const after=await sceneFacts(c);
  assert.equal(before.boats.length,3);assert.notDeepEqual(after.boats,before.boats);
  assert(after.frame-before.frame<=10,'unbounded idle animation');
  await c.page.emulateMedia({reducedMotion:'reduce'});await sleep(350);const stopped=await sceneFacts(c);await sleep(450);
  assert.deepEqual((await sceneFacts(c)).boats,stopped.boats);assert.equal((await sceneFacts(c)).frame,stopped.frame);
  await c.page.emulateMedia({reducedMotion:'no-preference'});
  // Controlled visibility event exercises cleanup even in headless Chrome with all tabs visible.
  await c.page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
  await sleep(300);const hidden=await sceneFacts(c);await sleep(400);assert.equal((await sceneFacts(c)).frame,hidden.frame);
  await c.page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  report.checks.push('capped Base motion / reduced-motion idle / visibility pause / 2D disposal');
}
async function reconnect(c,cs) {
  const id=c.match.match_id,tick=c.match.tick,history=c.room.chat_history.map(m=>m.text),tokens=c.tokens.length;
  await c.page.reload({waitUntil:'networkidle'});await h.wait(()=>c.tokens.length>tokens,'verified refresh reconnect');
  await c.page.locator('.game-shell').waitFor();await loaded(c);
  assert.equal(c.match.match_id,id);assert.equal(c.match.tick,tick);assert.deepEqual(c.room.chat_history.map(m=>m.text),history);
  assert(await c.page.getByLabel('Chat message',{exact:true}).isVisible());h.privacy(cs);
  report.checks.push('guest refresh / same match state / restored permanent chat');
}
async function natural(browser) {
  const cs=await h.room(browser,'direct',2,true,'base_standard',{visibleBank:true}),a=cs[0];
  for(const c of cs){await c.page.setViewportSize({width:1920,height:1080});await loaded(c);}
  while(a.match.state.phase==='setup') {
    const c=cs[a.match.state.turn],s=c.match.state,settle=s.setup_need==='settlement';
    await h.action(cs,c,()=>h.clickTarget(c,settle?'vertex':'edge',settle?s.legal.settlements[0]:s.legal.roads[0]),'natural placement');
  }
  await h.action(cs,a,()=>a.page.getByRole('button',{name:'Roll',exact:true}).click(),'natural Roll');
  assert.equal(a.match.state.rolled,true);assert.equal(a.match.state.pending_action,null);
  await sleep(2800);await shot(a,'base-normal-1920');
  const facts=await sceneFacts(a);assert.equal(facts.ocean,1);assert.equal(facts.badScenery.length,0);
  assert.equal(facts.ports.length,a.match.state.ports.length);
  assert(facts.ports.some(p=>p.ratio==='3:1'));
  for(const resource of ['wood','brick','sheep','wheat','ore'])assert(facts.ports.some(p=>p.resource===resource&&p.ratio==='2:1'));
  report.performance.push({map:'base_standard',...(await performance(a))});
  await chat(cs);await motion(a);await camera(a);
  await a.page.getByRole('button',{name:'Game info',exact:true}).click();
  const panel=a.page.getByRole('dialog',{name:'Game info',exact:true});assert(await panel.getByText(/Enable Test Room in the lobby/).isVisible());
  const p=await panel.boundingBox(),sidebar=await a.page.locator('.game-sidebar').boundingBox();assert(p.x+p.width<=sidebar.x,'info covers chat');
  await panel.getByRole('button',{name:'Close Game info',exact:true}).click();
  for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1280,height:720},{width:1024,height:768},{width:900,height:800}]) {
    await layout(a,size);if(size.width===1024)await shot(a,'base-narrow-1024');
    await a.page.getByRole('button',{name:'Event log',exact:true}).click();await layout(a,size);
    await a.page.getByRole('button',{name:'Event log',exact:true}).click();
  }
  await reconnect(a,cs);await h.action(cs,a,()=>a.page.getByRole('button',{name:'End Turn',exact:true}).click(),'natural End');
  report.checks.push('natural Base setup / Roll / End / all ports / responsive chat');
  await close(cs);
}
async function testAndActions(browser) {
  const cs=await h.room(browser,'direct',2,false,'base_standard',{testMode:true,visibleBank:true}),a=cs[0];
  for(const c of cs){await c.page.setViewportSize({width:1920,height:1080});await loaded(c);}
  assert(a.match.state.test_tools);for(const c of cs.slice(1))assert.equal(await c.page.getByRole('button',{name:'Test Tools',exact:true}).count(),0);
  let panel=await tools(a);await shot(a,'test-mode-active-1920');
  await panel.getByLabel('Test resource',{exact:true}).selectOption('wood');await panel.getByLabel('Test amount',{exact:true}).fill('4');
  const wood=h.own(a).res.wood;await testAction(cs,panel,'Give resources');assert.equal(h.own(a).res.wood,wood+4);
  await panel.getByLabel('Test amount',{exact:true}).fill('1');await testAction(cs,panel,'Remove resources');assert.equal(h.own(a).res.wood,wood+3);
  await closeTools(panel);
  const b=cs[1], beforeDenied=JSON.stringify(b.match.state), previousTokens=b.tokens.length;
  await h.action(cs,b,()=>b.page.evaluate(m=>window.__sockets.at(-1).send(JSON.stringify({type:'cmd',room_code:m.room_code,
    match_id:m.match_id,seq:1,cmd_id:'polish-participant-denial',cmd:{type:'test_action',action:'give_resources',player:0,resource:'wood',amount:1}})),b.match),
    'participant test denial',true);
  assert.equal(b.errors.at(-1).code,'forbidden');assert.equal(JSON.stringify(b.match.state),beforeDenied);
  await b.page.evaluate(()=>window.__sockets.at(-1).close());await h.wait(()=>b.tokens.length>previousTokens,'participant verified reconnect after denied command');
  await h.action(cs,a,()=>a.page.getByRole('button',{name:'City',exact:true}).click().then(()=>h.clickTarget(a,'vertex',a.match.state.legal.cities[0])),'paid city');
  await a.page.getByRole('button',{name:'Road',exact:true}).click();let edge=a.match.state.legal.roads[0];
  await h.action(cs,a,()=>h.clickTarget(a,'edge',edge),'paid road');assert.equal(a.match.state.occupied_e[edgeId(edge)],0);
  for(let i=0;!a.match.state.legal.settlements.length&&i<2;i++) {
    edge=a.match.state.legal.roads.find(e=>e.includes(edge[1]))??a.match.state.legal.roads[0];
    await h.action(cs,a,()=>h.clickTarget(a,'edge',edge),'extend paid route');
  }
  assert(a.match.state.legal.settlements.length);
  await a.page.getByRole('button',{name:'Settlement',exact:true}).click();const vertex=a.match.state.legal.settlements[0];
  await h.action(cs,a,()=>h.clickTarget(a,'vertex',vertex),'paid settlement');assert.deepEqual(a.match.state.occupied_v[vertex],[0,1]);
  await a.page.locator('.resource-hand button[data-resource="wood"]').click();
  const tray=a.page.getByRole('dialog',{name:'Trade tray',exact:true});
  const ratio=Number((await tray.getByLabel(/Trade ratio/).getAttribute('aria-label')).match(/\d+/)[0]);
  for(let i=1;i<ratio;i++)await a.page.locator('.resource-hand button[data-resource="wood"]').click();
  await tray.getByRole('button',{name:'Want ore',exact:true}).click();
  await h.action(cs,a,()=>tray.getByRole('button',{name:'Bank',exact:true}).click(),'bank trade');
  await a.page.locator('.resource-hand button[data-resource="sheep"]').click();
  await a.page.getByRole('dialog',{name:'Trade tray'}).getByRole('button',{name:'Want wheat',exact:true}).click();
  await h.action(cs,a,()=>a.page.getByRole('button',{name:'Offer to Players',exact:true}).click(),'broadcast offer');
  await h.action(cs,cs[1],()=>cs[1].page.getByRole('button',{name:'Accept',exact:true}).click(),'accept offer');
  await h.action(cs,a,()=>a.page.locator('.dev-mini-card').filter({hasText:'Knight'}).click(),'Knight');
  const legal=a.match.state.legal,tile=legal.robber_tiles.find(i=>legal.robber_victims[i]?.length),victim=legal.robber_victims[tile][0];
  if(legal.robber_victims[tile].length>1) {
    await h.clickTarget(a,'tile',tile);await h.action(cs,a,()=>a.page.getByRole('button',{name:a.match.state.players[victim].name,exact:true}).click(),'robber victim');
  } else await h.action(cs,a,()=>h.clickTarget(a,'tile',tile),'robber theft');
  const theft=a.match.state.game_events.findLast(e=>e.type==='theft');assert(theft?.resource);
  for(const c of cs) {
    await c.page.getByRole('button',{name:'Event log',exact:true}).click();
    const text=await c.page.locator('[data-event-type="theft"]').last().innerText();
    assert.equal(text.includes(theft.resource),[0,victim].includes(c.match.state.you_pid));
  }
  h.privacy(cs);
  // Force the existing host turn and dice through the existing validated controls.
  panel=await tools(a);await panel.getByLabel('Test player',{exact:true}).selectOption('0');await testAction(cs,panel,'Force turn');
  const s=a.match.state,t=s.tiles.findIndex((t,i)=>i!==s.robber_tile&&t.number&&Object.entries(s.occupied_v).some(([v,p])=>p[0]===0&&s.vertex_adj_hexes[v].includes(i)));
  const total=s.tiles[t].number;
  await panel.getByLabel('Next die 1',{exact:true}).selectOption(String(Math.max(1,total-6)));
  await panel.getByLabel('Next die 2',{exact:true}).selectOption(String(Math.min(6,total-1)));await testAction(cs,panel,'Set next dice');await closeTools(panel);
  const before={...h.own(a).res};await h.action(cs,a,()=>a.page.getByRole('button',{name:'Roll',exact:true}).click(),'controlled production');
  const production=a.match.state.game_events.findLast(e=>e.type==='production'&&e.player_pid===0);assert(production?.resources);
  for(const [r,n] of Object.entries(production.resources))assert.equal(h.own(a).res[r],before[r]+n);
  await layout(a,{width:1280,height:720});await layout(a,{width:1024,height:768});
  report.checks.push('gated Test Room host / participant hidden tools and real forbidden ACK / real give-remove / paid city-road-settlement / bank-player trades / dice-production');
  await close(cs);
}
async function theftPrivacy(browser) {
  const cs=await h.room(browser,'direct',3,false,'base_standard',{visibleBank:true}),a=cs[0];
  for(const c of cs){await c.page.setViewportSize({width:1280,height:720});await loaded(c);}
  await h.action(cs,a,()=>a.page.locator('.dev-mini-card').filter({hasText:'Knight'}).click(),'three-player Knight');
  const l=a.match.state.legal,tile=l.robber_tiles.find(i=>l.robber_victims[i]?.length),victim=l.robber_victims[tile][0];
  if(l.robber_victims[tile].length>1) {
    await h.clickTarget(a,'tile',tile);await h.action(cs,a,()=>a.page.getByRole('button',{name:a.match.state.players[victim].name,exact:true}).click(),'three-player victim');
  }else await h.action(cs,a,()=>h.clickTarget(a,'tile',tile),'three-player theft');
  const theft=a.match.state.game_events.findLast(e=>e.type==='theft');assert(theft?.resource);
  for(const c of cs){
    await c.page.getByRole('button',{name:'Event log',exact:true}).click();
    const text=await c.page.locator('[data-event-type="theft"]').last().innerText();
    assert.equal(text.includes(theft.resource),[0,victim].includes(c.match.state.you_pid));
    await layout(c,{width:1280,height:720});
  }
  h.privacy(cs);report.checks.push('three-player theft / participant face vs observer generic log / compact expanded-log layout');await close(cs);
}
async function gold(browser) {
  const cs=await h.room(browser,'gold',2,false,'seafarers_gold_haven',{visibleBank:true}),a=cs[0];
  await a.page.setViewportSize({width:1920,height:1080});await loaded(a);
  const edge=a.match.state.legal.ships[0];await a.page.getByRole('button',{name:'Ship',exact:true}).click();
  await h.action(cs,a,()=>h.clickTarget(a,'edge',edge),'build ship');assert.equal(a.match.state.occupied_ships[edgeId(edge)],0);
  await a.page.getByRole('button',{name:'Move Ship',exact:true}).click();
  const source=a.match.state.legal.move_ship.sources[0],target=a.match.state.legal.move_ship.targets[edgeId(source)][0];
  await h.clickTarget(a,'edge',source);await h.action(cs,a,()=>h.clickTarget(a,'edge',target),'move ship');
  assert.equal(a.match.state.occupied_ships[edgeId(target)],0);
  await h.action(cs,a,()=>a.page.locator('.dev-mini-card').filter({hasText:'Knight'}).click(),'Gold Knight');
  await a.page.getByRole('button',{name:'Pirate',exact:true}).click();const l=a.match.state.legal,tile=l.pirate_tiles.find(i=>!l.pirate_victims[i]?.length);
  await h.action(cs,a,()=>h.clickTarget(a,'tile',tile),'move pirate');assert.equal(a.match.state.pirate_tile,tile);
  await sleep(2800);await shot(a,'seafarers-1920');
  const facts=await sceneFacts(a);assert.equal(facts.boats.length,0);assert.equal(facts.badScenery.length,0);
  assert(facts.assets.includes('sea')&&facts.assets.includes('gold'));
  report.performance.push({map:'seafarers_gold_haven',...(await performance(a))});
  await a.page.mouse.move(1,1);await sleep(500);const frame=(await sceneFacts(a)).frame;await sleep(450);assert.equal((await sceneFacts(a)).frame,frame);
  for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1280,height:720},{width:1024,height:768}])await layout(a,size);
  report.checks.push('Gold Haven confirmed / real Sea-Gold GLBs / ship placement-move / pirate / no ambient boats / idle demand');
  await close(cs);
}
async function offGates(browser) {
  const cs=await h.room(browser,'direct',2,false,'base_standard',{visibleBank:true}),a=cs[0];
  for(const c of cs)assert.equal(await c.page.getByRole('button',{name:'Test Tools',exact:true}).count(),0);
  await loaded(a);await a.page.setViewportSize({width:1920,height:1080});
  await a.page.getByRole('button',{name:'Game info',exact:true}).click();
  const panel=a.page.getByRole('dialog',{name:'Game info'});assert(await panel.getByText(/disabled on this server/).isVisible());
  await shot(a,'test-mode-unavailable-1920');await panel.getByRole('button',{name:'Close Game info'}).click();
  const before=JSON.stringify(a.match.state);await h.invalidNext(a,{type:'test_action',action:'give_resources',player:0,resource:'wood',amount:1});
  await h.action(cs,a,()=>a.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'OFF server debug denial',true);
  assert.equal(a.errors.at(-1).code,'forbidden');assert.equal(JSON.stringify(a.match.state),before);
  report.checks.push('OFF server / no dangerous controls / explanatory info / real forbidden ACK / unchanged game');await close(cs);
}
async function close(cs) { for(const c of cs){assert.deepEqual(c.jsErrors,[]);await c.context.close();} }
async function main() {
  await fs.mkdir(output,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
  const wrapped={newContext:options=>newContext(browser,options)};
  try {if(off)await offGates(wrapped);else {await natural(wrapped);await testAndActions(wrapped);await theftPrivacy(wrapped);await gold(wrapped);}}
  catch(e){let n=0;for(const context of contexts)for(const page of context.pages())try{await page.screenshot({path:path.join(output,`failure-${report.mode}-${n++}.png`)});}catch{};await fs.writeFile(path.join(output,'partial-'+report.mode+'.json'),JSON.stringify(report,null,2));throw e;}
  finally{await browser.close();}
  await fs.writeFile(path.join(output,'verification-'+report.mode+'.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
