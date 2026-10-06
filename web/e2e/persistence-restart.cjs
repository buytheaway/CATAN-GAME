// Real ordinary-room UI + PostgreSQL crash/restart smoke, isolated project only.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18081';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-persistence-1b-browser');
const h = require('./game-actions.cjs');
const project = 'catan-persistence-test';
const compose = ['compose', '-p', project, '-f', 'compose.yaml', '-f', 'tests/persistence.compose.yaml'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function docker(args) {
  const result = spawnSync('docker', args, { encoding: 'utf8', timeout: 90000 });
  if (result.status !== 0) throw Error('Docker operation failed: ' + args.slice(0,5).join(' ') + '\n' + result.stderr);
  return result.stdout;
}
function metadata(code) {
  // Read private durable state only inside backend, returning hashes/counters, never payload/token/seed.
  const script = `import asyncio,os,sys,json
from sqlalchemy import select
from app.persistence.db import configured_database
from app.persistence import models as m
from app.persistence.repositories import Repository
from app.persistence.recovery import restore_room,checksum
from app.persistence.snapshots import encode_snapshot
async def main():
 db=configured_database()
 async with db.sessions() as s:
  rid=(await s.execute(select(m.rooms.c.id).where(m.rooms.c.room_code==sys.argv[1]))).scalar_one()
 r=restore_room(await Repository(db).load(rid))
 print(json.dumps(dict(room_id=str(r.id),match_uuid=str(r.match_uuid),match_no=r.match_id,tick=r.tick,
  engine=checksum(encode_snapshot(r.game)).hex(),deck=checksum(r.game.dev_deck).hex(),bag=checksum(r.dice_bag).hex(),
  roll_count=r.roll_count,seq=[p.last_seq_applied for p in r.players])))
 await db.close()
asyncio.run(main())`;
  return JSON.parse(docker(['exec', `${project}-backend-1`, 'python', '-B', '-c', script, code]).trim());
}
function stable(c) {
  const state = structuredClone(c.match.state);
  delete state.turn_timer;
  return { match_id: c.match.match_id, tick: c.match.tick, state };
}
async function freshReconnect(c, code) {
  c.match = null; c.room = null;
  await c.page.reload({ waitUntil: 'networkidle' });
  await h.wait(() => c.match && c.room, 'refresh verified guest reconnect');
  assert.equal(c.room.room_code, code);
}
async function resolvePending(clients) {
  if (clients[0].match.state.pending_action === 'discard') {
    for (const c of clients) {
      const need = c.match.state.discard_required[String(c.match.state.you_pid)];
      if (!need) continue;
      const dialog = c.page.getByRole('dialog', { name: /^Discard \d+ cards$/ });
      await dialog.waitFor();
      let left = need;
      for (const [resource, count] of Object.entries(h.own(c).res)) {
        for (let i=0;i<Math.min(left,count);i++) await dialog.locator(`button[data-resource="${resource}"]`).click();
        left -= Math.min(left,count);
        if (!left) break;
      }
      await h.action(clients,c,()=>dialog.getByRole('button',{name:'Confirm Discard',exact:true}).click(),'ordinary discard');
    }
  }
  if (clients[0].match.state.pending_action === 'robber_move') {
    const c = clients[clients[0].match.state.turn];
    const legal = c.match.state.legal;
    const tile = legal.robber_tiles.find(t=>!(legal.robber_victims[t]?.length));
    assert.notEqual(tile,undefined);
    await h.action(clients,c,()=>h.clickTarget(c,'tile',tile),'ordinary robber');
  }
}
async function naturalSetup(clients) {
  for (const c of clients) await h.open3d(c);
  while (clients[0].match.state.phase==='setup') {
    const c=clients[clients[0].match.state.turn], s=c.match.state;
    if(s.setup_need==='settlement') {
      // Ordinary player choice based on visible terrain; ensure useful natural starting resources.
      const score=v=>{
        const tiles=s.vertex_adj_hexes[String(v)].map(i=>s.tiles[i]);
        const types=new Set(tiles.map(t=>t.terrain));
        return (types.has('forest')?40:0)+(types.has('hills')?40:0)
          +tiles.reduce((n,t)=>n+(t.number?6-Math.abs(7-t.number):0),0);
      };
      const vid=[...s.legal.settlements].sort((a,b)=>score(b)-score(a))[0];
      await h.action(clients,c,()=>h.clickTarget(c,'vertex',vid),'natural settlement');
    } else await h.action(clients,c,()=>h.clickTarget(c,'edge',s.legal.roads[0]),'natural road');
  }
}
async function fundRoad(clients,c) {
  const hand=h.own(c).res;
  const missing=['wood','brick'].find(r=>!hand[r]);
  if(!missing||!c.match.state.bank_available[missing]) return;
  const give=Object.keys(hand).find(r=>r!==missing&&hand[r]>=4);
  if(!give) return;
  await c.page.locator(`.resource-hand button[data-resource="${give}"]`).click();
  const tray=c.page.getByRole('dialog',{name:'Trade tray',exact:true});
  const ratio=Number((await tray.locator('.trade-ratio').innerText()).split(':')[0]);
  for(let i=1;i<ratio;i++) await c.page.locator(`.resource-hand button[data-resource="${give}"]`).click();
  await tray.getByRole('button',{name:`Want ${missing}`,exact:true}).click();
  await h.action(clients,c,()=>tray.getByRole('button',{name:'Bank',exact:true}).click(),'ordinary maritime funding');
}
async function main() {
  const output = process.env.CATAN_E2E_OUTPUT;
  await fs.mkdir(output,{recursive:true});
  const browser = await chromium.launch({ channel:'chrome',headless:true });
  const report = { date:new Date().toISOString(), chrome:browser.version(), project, checks:[] };
  const check = name => { report.checks.push(name); console.log(JSON.stringify({passed:true,check:name})); };
  let clients=[];
  try {
    clients=await h.room(browser,'roomuxhidden',2,true);
    await naturalSetup(clients); // Eight real UI placements; no initializer or resource grants.
    check('ordinary Base Standard setup, Balanced dice, Hidden bank, colors and chat');
    let built=false;
    for (let i=0;i<36&&!built;i++) {
      const c=clients[clients[0].match.state.turn];
      if (!c.match.state.rolled) await h.action(clients,c,()=>c.page.getByRole('button',{name:'Roll',exact:true}).click(),'funding roll');
      await resolvePending(clients);
      await fundRoad(clients,c);
      const edge=c.match.state.legal.roads[0];
      if (edge) {
        await c.page.getByRole('button',{name:'Road',exact:true}).click();
        await h.action(clients,c,()=>h.clickTarget(c,'edge',edge),'ordinary paid road');
        assert.equal(c.match.state.occupied_e[[...edge].sort((a,b)=>a-b).join(',')],c.match.state.you_pid);
        built=true;
      } else await h.action(clients,c,()=>c.page.getByRole('button',{name:'End Turn',exact:true}).click(),'funding next turn');
    }
    assert(built,'A genuine resource-funded road is required for acceptance');
    check('paid road built through UI with naturally produced resources');
    const code=clients[0].room.room_code;
    const tokens=clients.map(c=>c.tokens.at(-1).reconnect_token);
    for (const c of clients) {
      await c.page.getByRole('button',{name:'Event log',exact:true}).click();
      await c.page.getByRole('tab',{name:'Chat',exact:true}).click();
    }
    await clients[0].page.getByLabel('Chat message',{exact:true}).fill('restart recovery <plain text>');
    await clients[0].page.getByRole('button',{name:'Send',exact:true}).click();
    await h.wait(()=>clients.every(c=>c.room.chat_history?.at(-1)?.text==='restart recovery <plain text>'),'committed game chat');
    const before=clients.map(stable), dbBefore=metadata(code);
    await freshReconnect(clients[0],code);
    assert.deepEqual(stable(clients[0]),before[0]);
    assert.equal(clients[0].tokens.at(-1).reconnect_token,tokens[0]);
    check('page refresh using existing Join/token flow');
    const counts=clients.map(c=>c.tokens.length);
    docker([...compose,'kill','-s','SIGKILL','backend']);
    docker([...compose,'up','-d','--wait','backend']);
    await h.wait(()=>clients.every((c,i)=>c.tokens.length>counts[i]&&c.match?.tick===dbBefore.tick),'two automatic reconnects after SIGKILL');
    for (let i=0;i<clients.length;i++) {
      assert.equal(clients[i].tokens.at(-1).reconnect_token,tokens[i]);
      assert.deepEqual(stable(clients[i]),before[i]);
      assert.equal(clients[i].room.chat_history.at(-1).text,'restart recovery <plain text>');
      assert(clients[i].match.state.turn_timer.remaining_ms>=19000);
    }
    assert.deepEqual(metadata(code),dbBefore);
    h.privacy(clients);
    check('backend SIGKILL: same room/match/full private digest/deck/bag/seq and both tokens');
    const active=clients[clients[0].match.state.turn];
    await h.action(clients,active,()=>active.page.getByRole('button',{name:'End Turn',exact:true}).click(),'post-recovery End Turn');
    const after=clients.map(stable), dbAfter=metadata(code), counts2=clients.map(c=>c.tokens.length);
    docker([...compose,'restart','backend']);
    await h.wait(()=>clients.every((c,i)=>c.tokens.length>counts2[i]&&c.match?.tick===dbAfter.tick),'second backend restart');
    clients.forEach((c,i)=>assert.deepEqual(stable(c),after[i]));
    assert.deepEqual(metadata(code),dbAfter);
    check('second backend restart preserves action accepted after first recovery');
    // A real database outage must reject publication, then retry exactly once after DB returns.
    const actor=clients[clients[0].match.state.turn], count=actor.sent.length;
    docker([...compose,'stop','postgres']);
    await actor.page.getByRole('button',{name:'Roll',exact:true}).click();
    await h.wait(()=>actor.sent.length>count&&actor.errors.some(e=>e.code==='persistence_unavailable'),'DB outage retryable failure');
    const pending=actor.sent[count];
    assert(!actor.acks.some(a=>a.cmd_id===pending.cmd_id));
    assert.equal(actor.match.tick,dbAfter.tick);
    docker([...compose,'up','-d','--wait','postgres']);
    await h.wait(()=>actor.acks.some(a=>a.cmd_id===pending.cmd_id),'DB restart pending command settled');
    await h.wait(()=>clients.every(c=>c.match.tick===dbAfter.tick+1),'single committed roll after DB returns');
    assert.equal(actor.match.state.roll_count,dbAfter.roll_count+1);
    h.privacy(clients);
    check('PostgreSQL stop/start retains volume: no success during outage, one replayed Roll');
    const dbFinal=metadata(code), final=clients.map(stable), counts3=clients.map(c=>c.tokens.length);
    docker([...compose,'down']); // Deliberately WITHOUT -v.
    docker([...compose,'up','-d','--wait']);
    await h.wait(()=>clients.every((c,i)=>c.tokens.length>counts3[i]&&c.match?.tick===dbFinal.tick),'full stack volume recovery');
    assert.deepEqual(metadata(code),dbFinal);
    clients.forEach((c,i)=>assert.deepEqual(stable(c),final[i]));
    check('full compose down/up without -v restores durable match');
    for(const c of clients) assert.deepEqual(c.jsErrors,[]);
    await h.evidence(clients[0],'recovered-board');
    report.gameplayCommands=clients.reduce((n,c)=>n+c.sent.length,0);
    if (process.env.CATAN_PERSISTENCE_DELETE_TEST_VOLUME==='1') {
      const volume=`${project}_postgres_data`;
      const info=JSON.parse(docker(['volume','inspect',volume]))[0];
      assert.equal(info.Labels['com.docker.compose.project'],project);
      assert.equal(info.Name,volume);
      await Promise.all(clients.map(c=>c.context.close()));clients=[];
      docker([...compose,'down','-v']); // Explicit flag + verified isolated volume; never ordinary suite default.
      docker([...compose,'up','-d','--wait']);
      const count=docker(['exec',`${project}-postgres-1`,'psql','-U','catan','-d','catan','-At','-c','SELECT count(*) FROM rooms;']).trim();
      assert.equal(count,'0');
      check('explicit isolated down -v deletes durable data as expected');
    }
    report.passed=true;
  } catch(error) {
    report.passed=false;report.error=String(error);
    if(clients[0]) await h.evidence(clients[0],'failure');
    throw error;
  } finally {
    const name=process.env.CATAN_PERSISTENCE_DELETE_TEST_VOLUME==='1'?'restart-volume-delete-results.json':'restart-results.json';
    await fs.writeFile(path.join(output,name),JSON.stringify(report,null,2));
    for(const c of clients) await c.context.close();
    await browser.close();
  }
}
if (require.main === module) main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports = { docker, compose, metadata, stable, freshReconnect, naturalSetup, resolvePending };
