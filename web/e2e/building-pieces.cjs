// Production dist + real isolated fixture_server/WS. Playwright is an external test tool.
// Funded/card/result states use the existing engine-built initializer, never fake snapshots.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const {chromium} = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18765';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-building-pieces-phase3b');
const h = require('./game-actions.cjs'), origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const dist = path.resolve(__dirname, '../dist'), sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = {checks: [], performance: [], layouts: [], commands: 0, expectedRejections: 0};
const contexts = [], edgeId = edge => [...edge].sort((a,b) => a-b).join(',');
const palette = {red:'#ef4444',blue:'#3b82f6',orange:'#f59e0b',white:'#f2f4f8',green:'#22c55e',purple:'#a855f7'};
async function newContext(browser, options, missing = false, missingTerrain = false) {
  const context = await browser.newContext(options); contexts.push(context); context.modelRequests = [];
  context.missingPieces = missing; context.missingTerrain = missingTerrain;
  await context.grantPermissions(['local-network-access'], {origin});
  await context.route(origin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/' || pathname.startsWith('/assets/') || pathname.startsWith('/models/')) {
      if (pathname.startsWith('/models/')) context.modelRequests.push(pathname);
      if ((missing && pathname.startsWith('/models/pieces/')) || (missingTerrain && pathname.startsWith('/models/terrain/')))
        return route.fulfill({status:404,body:'Intentional missing model acceptance case'});
      const file = path.join(dist, pathname === '/' ? 'index.html' : pathname);
      await route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.html')?'text/html'
        :file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'model/gltf-binary'});
    } else await route.continue();
  });
  return context;
}
async function facts(c) {
  return c.page.evaluate(() => {
    const {scene,gl,camera}=window.__scene.getState(); scene.updateMatrixWorld(true);
    const pieces=[],targets=[],terrains=[];let coastMaxY=-Infinity;
    scene.traverse(root => {
      const d=root.userData;
      if(d.terrainAsset)terrains.push(d.terrainAsset);
      if(d.coastEdge){const p=root.geometry.attributes.position;for(let i=0;i<p.count;i++)
        coastMaxY=Math.max(coastMaxY,root.position.clone().set(p.getX(i),p.getY(i),p.getZ(i)).applyMatrix4(root.matrixWorld).y);}
      if(d.targetType)targets.push(d.targetType==='vertex'?`v:${d.vertexId}`:`e:${d.edge.join(',')}`);
      if((d.piece!=='road' && !d.level) || !root.visible) return;
      let asset=null,fallback=null,appearing=false,minY=Infinity,badRaycast=0;
      const materials=[],geometries=[],nodes=[];
      root.traverse(o => {
        if(o.userData.pieceAsset)asset=o.userData.pieceAsset;
        if(o.userData.pieceFallback)fallback=o.userData.pieceFallback;
        if(o.userData.appearing)appearing=true;
        if(!o.isMesh)return;
        const hits=[];try{o.raycast({ray:null},hits);if(hits.length)badRaycast++;}catch{badRaycast++;}
        geometries.push(o.geometry.uuid);nodes.push(o.uuid);
        for(const m of Array.isArray(o.material)?o.material:[o.material])materials.push({name:m.name,color:'#'+m.color.getHexString(),uuid:m.uuid,opacity:m.opacity});
        const p=o.geometry.attributes.position;
        for(let i=0;i<p.count;i++) {
          const point=o.position.clone().set(p.getX(i),p.getY(i),p.getZ(i)).applyMatrix4(o.matrixWorld);minY=Math.min(minY,point.y);
        }
      });
      pieces.push({key:d.piece==='road'?`e:${d.edge.join(',')}`:`v:${d.vertexId}`,owner:d.owner,level:d.level,
        preview:!!d.preview,position:root.position.toArray(),rotation:root.rotation.y,asset,fallback,appearing,minY,badRaycast,materials,geometries,nodes});
    });
    return {pieces,targets,terrains,coastMaxY,frame:gl.info.render.frame,camera:camera.position.toArray()};
  });
}
async function loaded(c, missing = false) {
  await h.open3d(c);
  await c.page.waitForFunction(({missing,missingTerrain}) => {
    let terrains=0,ready=0,expected=0;
    window.__scene?.getState().scene.traverse(o=>{
      if(o.userData.terrainAsset || (missingTerrain && o.userData.terrainFallback))terrains++;
      if(o.userData.piece==='road'||o.userData.level){expected++;o.traverse(n=>{if(missing?n.userData.pieceFallback:n.userData.pieceAsset)ready++;});}
    });
    return terrains===Number(document.querySelector('.board3d')?.dataset.tileCount)&&ready===expected;
  },{missing,missingTerrain:c.context.missingTerrain});
}
async function verify(c, missing = false) {
  await loaded(c,missing);await c.page.mouse.move(1,1);await sleep(350);
  const f=await facts(c),s=c.match.state,real=f.pieces.filter(p=>!p.preview);
  assert(f.coastMaxY<=.21833333333333332+1e-6,'coastal strip stays below piece foundations');
  assert.equal(real.length,Object.keys(s.occupied_v).length+Object.keys(s.occupied_e).length);
  assert.equal(new Set(real.map(p=>p.key)).size,real.length,'one visual per original ID');
  for(const p of real) {
    const owned=s.players.find(player=>player.pid===p.owner);assert(owned);
    const material=p.materials.filter(m=>m.name==='PlayerColor');
    if(!missing){assert.equal(p.fallback,null);assert(p.asset);assert(material.length);material.forEach(m=>assert.equal(m.color,palette[owned.color]));}
    else { assert(p.fallback&&!p.asset); assert(p.materials.some(material=>material.color===palette[owned.color]),'fallback preserves ownership color'); }
    assert.equal(p.badRaycast,0);assert.equal(p.appearing,false,'finite motion settled');
    assert(Math.abs(p.minY-.21833333333333332)<.002,'common rim contact: '+JSON.stringify(p));
    if(p.key.startsWith('v:')) {
      const id=p.key.slice(2);assert.deepEqual([p.owner,p.level],s.occupied_v[id]);
      assert.deepEqual(p.position,[s.vertices[id][0]/s.size,.26,s.vertices[id][1]/s.size]);
    } else {
      assert.equal(p.owner,s.occupied_e[p.key.slice(2)]);
      const [a,b]=p.key.slice(2).split(',').map(id=>s.vertices[id]);
      assert.deepEqual(p.position,[(a[0]/s.size+b[0]/s.size)/2,.26+.06,(a[1]/s.size+b[1]/s.size)/2]);
      assert(Math.abs(p.rotation+Math.atan2(b[1]-a[1],b[0]-a[0]))<1e-10);
    }
  }
  assert.deepEqual(c.jsErrors,[]);h.privacy([c]);return f;
}
async function hoverTarget(c,type,id) {
  const key=type==='edge'?edgeId(id):id;
  await c.page.waitForFunction(({type,key})=>{let found=false;window.__scene?.getState().scene.traverse(o=>{
    if(o.userData.targetType===type&&(type==='edge'?o.userData.edge.join(',')===key:o.userData.vertexId===key))found=true;});return found;},{type,key});
  const p=await c.page.evaluate(({type,key})=>{
    const {scene,camera,gl}=window.__scene.getState();scene.updateMatrixWorld(true);let target;
    scene.traverse(o=>{if(o.userData.targetType===type&&(type==='edge'?o.userData.edge.join(',')===key:o.userData.vertexId===key))target=o;});
    const point=target.getWorldPosition(target.position.clone()).project(camera),r=gl.domElement.getBoundingClientRect();
    return {x:r.x+(point.x+1)*r.width/2,y:r.y+(1-point.y)*r.height/2};
  },{type,key});
  await c.page.mouse.move(p.x,p.y);await sleep(60);return p;
}
async function preview(c,kind,id) {
  const before=JSON.stringify(c.match.state),sent=c.sent.length,key=kind==='road'?`e:${edgeId(id)}`:`v:${id}`;
  await hoverTarget(c,kind==='road'?'edge':'vertex',id);
  await c.page.waitForFunction(({key,kind})=>{let found=false;window.__scene?.getState().scene.traverse(o=>{
    const d=o.userData;if(d.preview&&(d.piece==='road'?`e:${d.edge.join(',')}`:`v:${d.vertexId}`)===key)
      o.traverse(n=>{if(n.userData.pieceAsset===kind)found=true;});});return found;},{key,kind});
  const f=await facts(c),ghost=f.pieces.find(p=>p.preview&&p.key===key);assert(ghost);
  ghost.materials.forEach(m=>{assert.equal(m.opacity,.46);if(m.name==='PlayerColor')assert.equal(m.color,palette[h.own(c).color]);});
  assert.equal(ghost.badRaycast,0);
  if(kind==='city')assert.equal(f.pieces.filter(p=>p.key===key).length,1,'City preview replaces settlement, no stack');
  assert.equal(JSON.stringify(c.match.state),before);assert.equal(c.sent.length,sent);return ghost;
}
async function runAction(cs,c,run,label,rejected=false) {
  await h.action(cs,c,run,label,rejected);report.commands++;if(rejected)report.expectedRejections++;
}
async function shot(c,name){await c.page.screenshot({path:path.join(output,name+'.png')});}
async function close(cs){for(const c of cs){
  assert.deepEqual(c.jsErrors,[]);
  const unexpected=c.console.filter(message=>!message.includes('status of 503')
    &&!(c.context.missingPieces&&(message.includes('status of 404')||message.includes('using procedural piece fallback')))
    &&!(c.context.missingTerrain&&(message.includes('status of 404')||message.includes('using procedural terrain fallback'))));
  assert.deepEqual(unexpected,[],'unexpected WebGL/browser warnings');await c.context.close();
}}
async function natural(browser,map='base_standard') {
  const cs=await h.room(browser,'direct',2,true,map),a=cs[0];
  for(const c of cs)await loaded(c);
  let steps=0,coastal=false;
  while(a.match.state.phase==='setup') {
    const c=cs[a.match.state.turn],s=c.match.state,isSettlement=s.setup_need==='settlement';
    let id=isSettlement?s.legal.settlements[0]:s.legal.roads[0];
    if(isSettlement&&map!=='base_standard'&&!coastal){
      const v=s.legal.settlements.find(v=>s.vertex_adj_hexes[v].some(i=>s.tiles[i].terrain==='sea')&&s.vertex_adj_hexes[v].some(i=>s.tiles[i].terrain!=='sea'));
      assert.notEqual(v,undefined);id=v;coastal=true;
    }
    await preview(c,isSettlement?'settlement':'road',id);
    await c.page.keyboard.press('Escape');assert.equal(await c.page.getByRole('button',{name:'Cancel',exact:true}).count(),0);
    if(steps===1&&map==='base_standard') {
      await c.page.getByRole('button',{name:'2D',exact:true}).click();
      await runAction(cs,c,()=>c.page.locator(`[data-target-edge="${edgeId(id)}"]`).click(),'natural SVG setup road');
      await loaded(c);
    } else await runAction(cs,c,()=>h.clickTarget(c,isSettlement?'vertex':'edge',id),'natural '+s.setup_need);
    steps++;
  }
  assert.equal(steps,8);assert.equal(Object.keys(a.match.state.occupied_v).length,4);
  for(const c of cs)await verify(c);
  await runAction(cs,a,()=>a.page.getByRole('button',{name:'Roll',exact:true}).click(),'natural Roll');
  assert.equal(a.match.state.pending_action,null);
  await runAction(cs,a,()=>a.page.getByRole('button',{name:'End Turn',exact:true}).click(),'natural End');
  if(map==='base_standard') {
    const b=cs[1],pid=b.match.state.you_pid,tick=b.match.tick,tokens=b.tokens.length;
    await b.page.evaluate(()=>window.__sockets.at(-1).close());await h.wait(()=>b.tokens.length>tokens,'automatic token reconnect');
    assert.equal(b.match.state.you_pid,pid);assert.equal(b.match.tick,tick);await verify(b);
    b.match=null;await b.page.reload({waitUntil:'networkidle'});await h.wait(()=>b.match?.tick===tick,'refresh automatic Continue');await verify(b);
    const before=JSON.stringify(a.match),sent=a.sent.length,initial=(await facts(a)).camera,box=await a.page.locator('canvas').boundingBox();
    await a.page.mouse.move(box.x+box.width*.2,box.y+box.height*.5);await a.page.mouse.down();
    await a.page.mouse.move(box.x+box.width*.28,box.y+box.height*.55,{steps:8});await a.page.mouse.up();await sleep(180);
    assert.notDeepEqual((await facts(a)).camera,initial);await a.page.mouse.wheel(0,-120);
    await a.page.getByRole('button',{name:'Reset Camera'}).click();
    const requests=a.context.modelRequests.filter(p=>p.startsWith('/models/pieces/')).length;
    await a.page.getByRole('button',{name:'2D',exact:true}).click();await loaded(a);await verify(a);
    assert.equal(a.context.modelRequests.filter(p=>p.startsWith('/models/pieces/')).length,requests);
    assert.equal(JSON.stringify(a.match),before);assert.equal(a.sent.length,sent);
    report.checks.push('Base natural first/second setup settlement and road, SVG placement, Roll/End, two colors, reconnect/refresh, camera and cached 2D/3D');
  } else report.checks.push('Gold Haven natural coastal settlement/setup, mixed terrain rim contact and Roll/End');
  await a.page.setViewportSize({width:1920,height:1080});await shot(a,map+'-setup');await close(cs);
}
async function paid(browser,missing=false,reduced=false) {
  const cs=await h.room(browser,'direct',2,false,'base_standard',{testMode:!missing&&!reduced}),a=cs[0];
  const suffix=a.context.missingTerrain?'-terrain-fallback':reduced?'-reduced':'';
  await a.page.setViewportSize({width:1920,height:1080});if(reduced)await a.page.emulateMedia({reducedMotion:'reduce'});
  for(const c of cs)await verify(c,missing);
  const city=a.match.state.legal.cities[0];await a.page.getByRole('button',{name:'City',exact:true}).click();
  if(!missing){await preview(a,'city',city);await shot(a,'city-preview'+suffix);
    const before=a.sent.length;
    await a.page.getByLabel('Chat message',{exact:true}).focus();await a.page.keyboard.press('Escape');
    assert.equal(await a.page.getByRole('button',{name:'City',exact:true}).getAttribute('aria-pressed'),'true','chat Escape does not cancel board');
    await a.page.getByRole('button',{name:'City',exact:true}).focus();await a.page.keyboard.press('Escape');
    assert.equal(await a.page.getByRole('button',{name:'City',exact:true}).getAttribute('aria-pressed'),'false');
    await a.page.waitForFunction(()=>{let count=0;window.__scene?.getState().scene.traverse(o=>{if(o.userData.preview)count++;});return count===0;});
    assert.equal((await facts(a)).pieces.filter(p=>p.preview).length,0);assert.equal(a.sent.length,before);
    await a.page.getByRole('button',{name:'City',exact:true}).click();await preview(a,'city',city);
  }
  await runAction(cs,a,()=>h.clickTarget(a,'vertex',city),'paid city');
  assert.deepEqual(a.match.state.occupied_v[city],[0,2]);
  if(reduced)assert((await facts(a)).pieces.every(p=>!p.appearing));
  else if(!missing)assert((await facts(a)).pieces.find(p=>p.key===`v:${city}`).appearing,'confirmed city animation');
  await verify(a,missing);
  const disabled=a.page.getByRole('button',{name:'City',exact:true});assert(await disabled.isDisabled());
  await disabled.locator('..').hover();assert((await disabled.locator('..').getByRole('tooltip').innerText()).includes('Missing resources: 1 ore'));
  await a.page.getByRole('button',{name:'Road',exact:true}).click();let edge=a.match.state.legal.roads[0];
  if(!missing) {
    await preview(a,'road',edge);
    const before=JSON.stringify(a.match.state),old=(await facts(a)).pieces.filter(p=>!p.preview).map(p=>[p.key,p.nodes]);
    await h.invalidNext(a,{type:'place_road',eid:[99999,99998]});
    await runAction(cs,a,()=>h.clickTarget(a,'edge',edge),'rejected build coordinate',true);
    assert.equal(JSON.stringify(a.match.state),before);
    assert.deepEqual((await facts(a)).pieces.filter(p=>!p.preview).map(p=>[p.key,p.nodes]),old,'rejection preserves existing GLB nodes');
    const upgrade=Object.entries(a.match.state.occupied_v).find(([,piece])=>piece[0]===0&&piece[1]===1);assert(upgrade);
    await h.invalidNext(a,{type:'upgrade_city',vid:Number(upgrade[0])});
    await runAction(cs,a,()=>h.clickTarget(a,'edge',edge),'rejected unaffordable upgrade',true);
    assert.equal(JSON.stringify(a.match.state),before);assert.deepEqual(a.match.state.occupied_v[upgrade[0]],[0,1]);
  }
  await runAction(cs,a,()=>h.clickTarget(a,'edge',edge),'paid road');
  for(let n=0;!a.match.state.legal.settlements.length&&n<2;n++) {
    edge=a.match.state.legal.roads.find(e=>e.includes(edge[1]))??a.match.state.legal.roads[0];assert(edge);
    await runAction(cs,a,()=>h.clickTarget(a,'edge',edge),'extend paid road');
  }
  const vertex=a.match.state.legal.settlements[0];assert.notEqual(vertex,undefined);
  await a.page.getByRole('button',{name:'Settlement',exact:true}).click();if(!missing)await preview(a,'settlement',vertex);
  await runAction(cs,a,()=>h.clickTarget(a,'vertex',vertex),'paid settlement');assert.deepEqual(a.match.state.occupied_v[vertex],[0,1]);
  if(reduced)assert((await facts(a)).pieces.every(p=>!p.appearing));
  else if(!missing)assert((await facts(a)).pieces.find(p=>p.key===`v:${vertex}`).appearing,'confirmed settlement animation');
  await a.page.mouse.move(1,1);for(const c of cs)await verify(c,missing);
  if(!missing&&!reduced){
    assert.equal(await cs[1].page.getByRole('button',{name:'Test Tools',exact:true}).count(),0);
    await a.page.getByRole('button',{name:'Test Tools',exact:true}).click();
    const panel=a.page.getByRole('dialog',{name:'Test Tools',exact:true});await panel.getByLabel('Test player',{exact:true}).selectOption('0');
    const wood=h.own(a).res.wood;await panel.getByLabel('Test resource',{exact:true}).selectOption('wood');
    await runAction(cs,a,()=>panel.getByRole('button',{name:'Give resources',exact:true}).click(),'existing Test Mode give');
    assert.equal(h.own(a).res.wood,wood+1);await panel.getByRole('button',{name:'Close Test Tools'}).click();
    const stable=(await facts(a)).pieces.map(p=>[p.key,p.nodes,p.geometries,p.materials.map(m=>m.uuid)]);
    await a.page.getByRole('button',{name:'Game info',exact:true}).click();await a.page.getByRole('button',{name:'Close Game info'}).click();
    assert.deepEqual((await facts(a)).pieces.map(p=>[p.key,p.nodes,p.geometries,p.materials.map(m=>m.uuid)]),stable,'ordinary UI rerender reuses scene resources');
    for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1280,height:720}]){
      await a.page.setViewportSize(size);await a.page.getByRole('button',{name:'Reset Camera'}).click();await sleep(200);
      const m=await h.boardMetrics(a);assert.equal(m.occludedByHud,0);assert(m.visible.top>=m.canvasBounds.top&&m.visible.bottom<=m.canvasBounds.bottom);
      assert(m.visible.left>=m.canvasBounds.left&&m.visible.right<=m.canvasBounds.right);report.layouts.push({map:'base_standard',size});
      await shot(a,'base-buildings-'+size.width+suffix);
    }
  }
  report.checks.push(a.context.missingTerrain?'Missing terrain GLBs: procedural board and all three building GLBs have shared contact, targeting/commands stay usable'
    :missing?'Missing all three GLBs: procedural city/road/settlement and commands remain usable':reduced?'Reduced motion: all three accepted construction types render without appearance animation'
    :'Paid City replacement/Escape and chat guard, costs, rejected coordinate/unchanged nodes, road/settlement ghosts and placement, Test Mode, responsive framing');
  if(missing){for(const kind of ['settlement','city','road'])assert.equal(a.console.filter(message=>message.includes(`/models/pieces/${kind}.glb; using procedural piece fallback`)).length,1);await shot(a,'missing-pieces-fallback');}
  if(a.context.missingTerrain)await shot(a,'missing-terrain-piece-contact');
  await close(cs);
}
async function freeRoads(browser) {
  const cs=await h.room(browser,'road'),a=cs[0];await loaded(a);const before={...h.own(a).res};
  await runAction(cs,a,()=>a.page.locator('.dev-mini-card').filter({hasText:'Road Building'}).click(),'Road Building before Roll');
  for(const step of [1,2]) {
    assert.equal(a.match.state.free_roads['0'],3-step);assert.equal(a.match.state.legal.road_free,true);
    const edge=a.match.state.legal.roads[0];await preview(a,'road',edge);
    await runAction(cs,a,()=>h.clickTarget(a,'edge',edge),'free road '+step);
    assert.equal(a.sent.at(-1).cmd.free,true);assert.deepEqual(h.own(a).res,before);
    assert((await facts(a)).pieces.find(p=>p.key===`e:${edgeId(edge)}`).appearing,'confirmed road animation');
  }
  assert.equal(a.match.state.free_roads['0'],0);assert.equal(a.match.state.rolled,false);await verify(a);
  await shot(a,'road-building-complete');report.checks.push('Road Building before Roll: two real GLB ghosts/accepted free roads, unchanged resources/counter lifecycle');await close(cs);
}
async function gold(browser) {
  const cs=await h.room(browser,'gold',2,false,'seafarers_gold_haven'),a=cs[0];await loaded(a);
  const s=a.match.state;
  const ship=s.legal.ships.find(edge=>s.legal.roads.some(road=>road.some(v=>edge.includes(v))))
    ??s.legal.ships.find(edge=>Object.keys(s.occupied_e).some(key=>s.occupied_e[key]===0&&key.split(',').map(Number).some(v=>edge.includes(v))));
  assert(ship,'legal ship beside a confirmed or available road');await a.page.getByRole('button',{name:'Ship',exact:true}).click();
  await runAction(cs,a,()=>h.clickTarget(a,'edge',ship),'Gold ship build');
  const adjacent=a.match.state.legal.roads.find(edge=>edge.some(v=>ship.includes(v)));
  if(!adjacent)assert(Object.keys(a.match.state.occupied_e).some(key=>a.match.state.occupied_e[key]===0&&key.split(',').map(Number).some(v=>ship.includes(v))),
    'confirmed setup road shares the newly built ship vertex');
  const road=adjacent??a.match.state.legal.roads[0];assert(road);
  await a.page.getByRole('button',{name:'Road',exact:true}).click();await preview(a,'road',road);
  await runAction(cs,a,()=>h.clickTarget(a,'edge',road),adjacent?'Gold road next to ship':'Gold paid road');
  await a.page.getByRole('button',{name:'Move Ship',exact:true}).click();
  const source=a.match.state.legal.move_ship.sources[0],destination=a.match.state.legal.move_ship.targets[edgeId(source)][0];assert(destination);
  await h.clickTarget(a,'edge',source);await runAction(cs,a,()=>h.clickTarget(a,'edge',destination),'Gold ship move');
  assert.equal(a.match.state.occupied_ships[edgeId(source)],undefined);assert.equal(a.match.state.occupied_ships[edgeId(destination)],0);
  await runAction(cs,a,()=>a.page.locator('.dev-mini-card').filter({hasText:'Knight'}).click(),'Gold Knight');
  await a.page.getByRole('button',{name:'Pirate',exact:true}).click();
  const l=a.match.state.legal,tile=l.pirate_tiles.find(i=>!l.pirate_victims[i]?.length);
  await runAction(cs,a,()=>h.clickTarget(a,'tile',tile),'Gold pirate');assert.equal(a.match.state.pirate_tile,tile);
  for(const c of cs)await verify(c);const f=await facts(a);assert(f.terrains.includes('sea')&&f.terrains.includes('gold'));
  await a.page.mouse.move(1,1);await sleep(500);const frame=(await facts(a)).frame;await sleep(400);assert.equal((await facts(a)).frame,frame,'Seafarers returns to zero idle frames');
  for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1280,height:720}]){
    await a.page.setViewportSize(size);await a.page.getByRole('button',{name:'Reset Camera'}).click();await sleep(220);
    const m=await h.boardMetrics(a);assert.equal(m.occludedByHud,0);assert(m.visible.top>=m.canvasBounds.top&&m.visible.bottom<=m.canvasBounds.bottom);
    report.layouts.push({map:'seafarers_gold_haven',size});await shot(a,'gold-buildings-'+size.width);
  }
  report.checks.push('Gold Haven sea/gold, GLB road beside new ship ('+(adjacent?'new road':'existing setup road')+'), paid road, ship build/move/pirate, shared rim contact, idle demand and desktop framing');await close(cs);
}
async function results(browser,disconnectedHost=false) {
  const cs=await h.room(browser,'results',disconnectedHost?3:2),a=cs[0];for(const c of cs)await verify(c);
  const colors=a.match.state.players.map(p=>p.color),old=a.match.match_id;
  await runAction(cs,a,()=>a.page.getByRole('button',{name:'Dev Card',exact:true}).click(),'winning development purchase');
  for(const c of cs){assert(c.match.state.game_over);await c.page.getByRole('dialog',{name:'Match results'}).waitFor();assert.equal((await facts(c)).targets.length,0);}
  await shot(a,'results-buildings'+(disconnectedHost?'-three-player':''));
  let retained=cs;
  if(disconnectedHost){await a.context.close();retained=cs.slice(1);await h.wait(()=>retained.every(c=>!c.room.players[0].connected),'old host disconnected');}
  const starter=retained[0];await starter.page.getByRole('button',{name:'Rematch',exact:true}).click();
  await h.wait(()=>retained.every(c=>c.match.match_id===old+1),'new authoritative match');
  for(const [pid,c] of retained.entries()){assert.equal(c.match.tick,0);assert.equal(c.match.state.phase,'setup');assert.equal(c.match.state.you_pid,pid);
    assert.deepEqual(c.match.state.players.map(p=>p.color),disconnectedHost?colors.slice(1):colors);
    assert.equal(Object.keys(c.match.state.occupied_v).length,0);assert.equal((await facts(c)).pieces.length,0);assert.equal(c.tokens.at(-1).last_seq_applied,0);}
  const vertex=starter.match.state.legal.settlements[0];await preview(starter,'settlement',vertex);
  await runAction(retained,starter,()=>h.clickTarget(starter,'vertex',vertex),'new match first settlement');assert.equal(starter.sent.at(-1).seq,1);
  await verify(starter);report.checks.push(disconnectedHost?'Three-player result/rematch after host disconnect: compact pids retain the old owner colors and new GLB setup placement'
    :'Game over stops legal targets; rematch clears visuals/sequence, retains colors and new setup placement');await close(retained);
}
async function main(){
  await fs.mkdir(output,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
  const wrapped={newContext:options=>newContext(browser,options)},missing={newContext:options=>newContext(browser,options,true)},
    missingTerrain={newContext:options=>newContext(browser,options,false,true)};
  try{await natural(wrapped);await paid(wrapped);await freeRoads(wrapped);await natural(wrapped,'seafarers_gold_haven');
    await gold(wrapped);await paid(wrapped,false,true);await results(wrapped);await results(wrapped,true);await paid(missing,true);await paid(missingTerrain);}
  catch(error){let n=0;for(const context of contexts)for(const page of context.pages())try{await page.screenshot({path:path.join(output,`failure-${n++}.png`)});}catch{};
    await fs.writeFile(path.join(output,'partial.json'),JSON.stringify(report,null,2));throw error;}
  finally{await browser.close();}
  await fs.writeFile(path.join(output,'verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1});
