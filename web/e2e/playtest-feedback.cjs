// UX 2.3: real production images, explicit test-room capabilities, real Chrome/WS.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { room, action, clickTarget, evidence, layout, boardMetrics, wait, own, privacy, open3d, invalidNext } = require('./game-actions.cjs');
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-game-ux-2-3');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const resources = ['wood', 'brick', 'sheep', 'wheat', 'ore'];

async function tools(c) {
  await c.page.getByRole('button', { name: 'Test Tools', exact: true }).click();
  const panel = c.page.getByRole('dialog', { name: 'Test Tools', exact: true });
  await panel.waitFor(); return panel;
}
async function testAction(cs, c, panel, name) {
  return action(cs, c, () => panel.getByRole('button', { name, exact: true }).click(), name);
}
async function force(cs, pid = 0) {
  const a = cs[0], panel = await tools(a);
  await panel.getByLabel('Test player', { exact: true }).selectOption(String(pid));
  await testAction(cs, a, panel, 'Force turn');
  await panel.getByRole('button', { name: 'Close Test Tools', exact: true }).click();
}
async function dice(cs, faces) {
  const a = cs[0], panel = await tools(a);
  for (let i = 0; i < 2; i++) await panel.getByLabel(`Next die ${i + 1}`, { exact: true }).selectOption(String(faces[i]));
  await testAction(cs, a, panel, 'Set next dice');
  for (const c of cs) assert(!('next_test_dice' in c.match.state));
  await panel.getByRole('button', { name: 'Close Test Tools', exact: true }).click();
}
async function deny(cs) {
  const a = cs[0], before = JSON.stringify(a.match.state);
  assert.equal(await a.page.getByRole('button', { name: 'Test Tools', exact: true }).count(), 0);
  await invalidNext(a, { type: 'test_action', action: 'set_next_dice', dice: [6, 1] });
  await action(cs, a, () => a.page.getByRole('button', { name: 'Dev Card', exact: true }).click(), 'debug rejected in normal room', true);
  assert.equal(a.errors.at(-1).code, 'forbidden'); assert.equal(JSON.stringify(a.match.state), before);
}
async function debugTools(cs) {
  const [a, b] = cs;
  assert.equal(await b.page.getByRole('button', { name: 'Test Tools', exact: true }).count(), 0);
  const panel = await tools(a), before = own(a).res.ore;
  await panel.getByLabel('Test resource', { exact: true }).selectOption('ore');
  await panel.getByLabel('Test amount', { exact: true }).fill('2');
  await testAction(cs, a, panel, 'Give resources'); assert.equal(own(a).res.ore, before + 2);
  await panel.getByLabel('Test amount', { exact: true }).fill('1');
  await testAction(cs, a, panel, 'Remove resources'); assert.equal(own(a).res.ore, before + 1);
  const cards = own(a).dev_cards.length;
  await panel.getByLabel('Test card', { exact: true }).selectOption('knight');
  await testAction(cs, a, panel, 'Give development card'); assert.equal(own(a).dev_cards.length, cards + 1);
  const immutable = JSON.stringify(a.match.state);
  await panel.getByLabel('Test amount', { exact: true }).fill('100');
  await action(cs, a, () => panel.getByRole('button', { name: 'Give resources', exact: true }).click(), 'invalid source quantity', true);
  assert.equal(JSON.stringify(a.match.state), immutable); assert(await panel.getByRole('alert').isVisible());
  await panel.getByRole('button', { name: 'Close Test Tools', exact: true }).click();
  // A participant still cannot cheat, even in an explicitly enabled room.
  const other = JSON.stringify(b.match.state);
  await invalidNext(b, { type: 'test_action', action: 'force_turn', player: 1 });
  // Test security directly with a valid real envelope, since ordinary off-turn UI is disabled.
  await b.page.evaluate(({ match, seq }) => window.__sockets.at(-1).send(JSON.stringify({ type: 'cmd',
    match_id: match.match_id, room_code: match.room_code, seq, cmd_id: 'participant-debug',
    cmd: { type: 'test_action', action: 'force_turn', player: 1 } })), { match: b.match, seq: 1 });
  await wait(() => b.acks.some(ack => ack.cmd_id === 'participant-debug'), 'participant debug ACK');
  assert.equal(b.acks.find(ack => ack.cmd_id === 'participant-debug').applied, false);
  assert.equal(JSON.stringify(b.match.state), other);
  // Remove fault injection after the direct security probe, then recover token/sequence normally.
  await b.page.evaluate(() => { delete window.__nextInvalidCommand; window.__sockets.at(-1).close(); });
  await wait(() => b.tokens.at(-1)?.last_seq_applied === 1, 'participant reconnect consumes rejected sequence');
  await force(cs); await dice(cs, [4, 5]);
  await action(cs, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'forced next roll');
  cs.forEach(c => assert.deepEqual(c.match.state.dice, [4, 5]));
  const near = await tools(a);
  await testAction(cs, a, near, 'Near win'); assert.equal(own(a).vp, a.match.state.rules_config.target_vp - 1);
  await evidence(a, 'test-tools-near-win');
  await near.getByLabel('Test card', { exact: true }).selectOption('victory_point');
  await testAction(cs, a, near, 'Give development card');
  assert(a.match.state.game_over); assert.equal(a.match.state.winner_pid, 0);
  for (const c of cs) assert.equal(c.match.state.players[0].vp, a.match.state.rules_config.target_vp);
  privacy(cs);
}

async function production(cs) {
  const [a, b] = cs; await open3d(a); await open3d(b);
  const s = a.match.state;
  const tile = s.tiles.findIndex((t, i) => i !== s.robber_tile && t.number && !['gold','sea','desert'].includes(t.terrain)
    && Object.entries(s.occupied_v).some(([v, piece]) => piece[0] === 0 && s.vertex_adj_hexes[v].includes(i)));
  assert(tile >= 0); const total = s.tiles[tile].number;
  await force(cs); await dice(cs, [Math.max(1, total - 6), Math.min(6, total - 1)]);
  const before = { ...own(a).res };
  await action(cs, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'production roll');
  const event = a.match.state.game_events.findLast(e => e.type === 'production' && e.player_pid === 0);
  assert(event?.resources); assert(event.quantity > 0);
  for (const [r, q] of Object.entries(event.resources)) assert.equal(own(a).res[r], before[r] + q);
  const observer = b.match.state.game_events.find(e => e.id === event.id);
  assert(!('resources' in observer));
  await a.page.waitForFunction(() => [...document.querySelectorAll('.flying-card')].some(e => +getComputedStyle(e).opacity > .2));
  assert(await a.page.locator('.flying-card:not(.card-back)').count() > 0);
  assert(await b.page.locator('.flying-card.card-back').count() > 0);
  await evidence(a, 'production-self'); await evidence(b, 'production-observer');
  await sleep(2800); assert.equal(await a.page.locator('.flying-card').count(), 0);
  const frames = await a.page.evaluate(() => window.__scene.getState().gl.info.render.frame);
  await sleep(400); assert.equal(await a.page.evaluate(() => window.__scene.getState().gl.info.render.frame), frames);
  privacy(cs);
}

async function theft(cs) {
  const a = cs[0]; for (const c of cs) await open3d(c);
  await action(cs, a, () => a.page.locator('.dev-mini-card').filter({ hasText: 'Knight' }).click(), 'direct Knight theft');
  const legal = a.match.state.legal, tile = legal.robber_tiles.find(t => legal.robber_victims[t]?.length);
  assert.notEqual(tile, undefined); const victim = legal.robber_victims[tile][0];
  const position = c => c.page.evaluate(() => { let p; window.__scene.getState().scene.traverse(o => {
    if(o.userData.piece==='robber') p=o.position.toArray(); }); return p; });
  const old = await position(a);
  if (legal.robber_victims[tile].length > 1) {
    await clickTarget(a, 'tile', tile);
    await action(cs, a, () => a.page.getByRole('dialog', { name: 'Choose player' }).getByRole('button',
      { name: a.match.state.players.find(p => p.pid === victim).name, exact: true }).click(), 'choose actual victim');
  } else await action(cs, a, () => clickTarget(a, 'tile', tile), 'move and steal');
  const event = a.match.state.game_events.at(-1);
  assert.equal(event.type, 'theft'); assert.equal(event.victim_pid, victim); assert(event.resource);
  const during = await position(a); assert.notDeepEqual(during, old);
  for (const c of cs) {
    const e = c.match.state.game_events.at(-1), involved = [0, victim].includes(c.match.state.you_pid);
    assert.equal(e.type, 'theft'); assert.equal('resource' in e, involved);
    if (involved) assert.equal(e.resource, event.resource);
    const flight = c.page.locator(`.flying-card[data-flight="${involved ? event.resource : 'back'}"]`);
    assert(await flight.count() >= 1);
    await c.page.getByRole('button', { name: 'Event log', exact: true }).click();
    const text = await c.page.locator('[data-event-type="theft"]').innerText();
    assert(text.includes('stole') && text.includes(a.match.state.players[victim].name));
    assert.equal(text.includes(event.resource), involved);
  }
  await evidence(a, 'theft-thief'); await evidence(cs[victim], 'theft-victim');
  await evidence(cs.find(c => ![0, victim].includes(c.match.state.you_pid)), 'theft-observer');
  await sleep(500); const settled = await position(a); assert.notDeepEqual(during, settled);
  const center = a.match.state.tiles[tile].center, size = a.match.state.size;
  assert.ok(Math.abs(settled[0] - center[0] / size - .48) < 1e-6);
  assert.ok(Math.abs(settled[2] - center[1] / size - .1) < 1e-6);
  privacy(cs);
}

async function discard(cs) {
  const a = cs[0]; await force(cs);
  const panel = await tools(a);
  await testAction(cs, a, panel, 'Trigger seven');
  assert.equal(a.match.state.pending_action, 'discard');
  for (const c of cs) {
    const pid = c.match.state.you_pid, required = c.match.state.discard_required[pid];
    assert.equal(required, Math.floor(Object.values(own(c).res).reduce((n,v)=>n+v,0)/2));
    const modal = c.page.getByRole('dialog', { name: `Discard ${required} cards`, exact: true });
    await modal.waitFor(); assert.equal(await modal.locator('input[type=number]').count(), 0);
    assert(await modal.getByRole('button', { name: 'Confirm Discard' }).isDisabled());
    const have = own(c).res.wood;
    for(let i=0;i<have;i++) await modal.getByRole('button', {name:'Discard wood',exact:true}).click();
    assert(await modal.getByRole('button', {name:'Discard wood',exact:true}).isDisabled());
    await modal.getByRole('button', {name:'Remove discard wood',exact:true}).click();
    await modal.getByRole('button', {name:'Discard wood',exact:true}).click();
    let left = required - have;
    for (const r of resources.slice(1)) {
      const count = Math.min(left, own(c).res[r]); left -= count;
      for(let i=0;i<count;i++) await modal.getByRole('button', {name:`Discard ${r}`,exact:true}).click();
    }
    assert.equal(left,0); assert(await modal.getByRole('button',{name:'Confirm Discard'}).isEnabled());
    assert.equal(await modal.getByText(`Selected: ${required} / ${required}`, {exact:true}).count(),1);
    if(c===a) {
      await evidence(c,'discard-card-selector'); const before=JSON.stringify(c.match.state);
      await invalidNext(c,{type:'discard',discards:{wood:999}});
      await action(cs,c,()=>modal.getByRole('button',{name:'Confirm Discard'}).click(),'invalid discard stays atomic',true);
      assert.equal(JSON.stringify(c.match.state),before); assert(await modal.getByRole('alert').isVisible());
    }
    await action(cs,c,()=>modal.getByRole('button',{name:'Confirm Discard'}).click(),'confirm card discard');
  }
  assert.equal(a.match.state.pending_action,'robber_move');
  privacy(cs);
}

async function thresholdEqual(cs) {
  await force(cs); const panel=await tools(cs[0]); await testAction(cs,cs[0],panel,'Trigger seven');
  for(const c of cs) { assert.equal(c.match.state.pending_action,'robber_move'); assert.deepEqual(c.match.state.discard_required,{});
    assert.equal(c.match.state.rules_config.discard_threshold,25); }
}

async function fifty(cs) {
  const a=cs[0]; await open3d(a); await layout(a);
  a.measurements=[];
  for(const size of [{width:1920,height:1080},{width:1440,height:900},{width:1280,height:720}]) {
    await a.page.setViewportSize(size); await a.page.getByRole('button',{name:'Reset Camera'}).click();
    await a.page.mouse.move(1,1); await sleep(250); const m=await boardMetrics(a); a.measurements.push(m);
    assert.equal(m.tiles.length,50); assert.equal(m.occludedByHud,0);
    assert(m.visible.left>=m.canvasBounds.left && m.visible.right<=m.canvasBounds.right);
    assert(m.visible.top>=m.canvasBounds.top && m.visible.bottom<=m.canvasBounds.bottom);
    const frame=m.frame; await sleep(450); assert.equal(await a.page.evaluate(()=>window.__scene.getState().gl.info.render.frame),frame);
    assert.equal(await a.page.evaluate(()=>document.querySelector('[data-renderer="3d"]')?.dataset.tileCount),'50');
    await evidence(a,'fifty-'+size.width);
  }
  const resourcesBefore=await a.page.evaluate(()=>{const {gl}=window.__scene.getState();return {...gl.info.memory};});
  assert(resourcesBefore.geometries>0); await a.page.getByRole('button',{name:'2D',exact:true}).click();
  await sleep(250); const after=await a.page.evaluate(()=>({...window.__scene.getState().gl.info.memory}));
  assert.equal(after.geometries,0); assert.equal(after.textures,0);
}

async function main() {
  await fs.mkdir(output,{recursive:true}); const browser=await chromium.launch({channel:'chrome',headless:true});
  const mode=process.env.CATAN_TEST_MODE_CHECK || 'off';
  const terrain=['forest','hills','pasture','fields','mountains','desert','sea','gold'];
  const mapData={name:'fifty_hex_visual_fixture',version:1,size:58,tiles:Array.from({length:50},(_,i)=>({q:i%10+7,r:Math.floor(i/10)-6,
    terrain:terrain[i%8],number:['desert','sea'].includes(terrain[i%8])?null:[2,3,4,5,6,8,9,10,11,12][i%10]})),
    rules:{enable_seafarers:true,enable_pirate:true,enable_gold:true,enable_move_ship:true}};
  const cases=mode==='off' ? [['debugoff',2,deny,{}]] : [['normal',2,deny,{}], ['debugtools',2,debugTools,{testMode:true}],
    ['production',2,production,{testMode:true,visibleBank:true}], ['theft',3,theft,{}],
    ['discard',3,discard,{testMode:true,threshold:10}], ['threshold',3,thresholdEqual,{testMode:true,threshold:25}],
    ['fifty',2,fifty,{mapData}]];
  const report={date:new Date().toISOString(),chrome:browser.version(),mode,results:[]};
  try {
    for(const [name,count,run,options] of cases) {
      let cs=[];
      try {
        cs=await room(browser,name,count,false,'base_standard',options); await run(cs);
        for(const c of cs){assert.deepEqual(c.jsErrors,[]);assert.deepEqual(c.console,[]);}
        report.results.push({name,passed:true,commands:cs.flatMap(c=>c.sent.map(m=>m.cmd)),rejected:cs.flatMap(c=>c.errors),measurements:cs[0].measurements});
        console.log(JSON.stringify({name,passed:true}));
      } catch(error) { if(cs[0]) await evidence(cs[0],'failure-'+name); report.results.push({name,passed:false,error:String(error)}); throw error;
      } finally {for(const c of cs)await c.context.close();}
    }
  } finally { await fs.writeFile(path.join(output,'playtest-'+mode+'.json'),JSON.stringify(report,null,2)); await browser.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
