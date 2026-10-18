// Real Board3D using synthetic PUBLIC frames. No game rules or hidden assignment.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const { observeScene, ready, idleFrames } = require('./ships-visual.cjs');
const baseline = process.argv.includes('--baseline');
const reference = 'f315519f0d06cf5bf131f9bc2247e82c1c3abc64';
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-buildings-visual-phase3');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function info(page) {
  return page.evaluate(() => {
    const { scene, gl } = window.__scene.getState();
    const result = { pieces: [], echoes: 0, fog: 0, ships: 0, frames: gl.info.render.frame,
      geometries: gl.info.memory.geometries, textures: gl.info.memory.textures, commits: window.__sceneCommits };
    scene.traverse(o => {
      if (o.userData.piece === 'road' || o.userData.vertexId != null && o.userData.level) {
        const kind = o.userData.piece === 'road' ? 'road' : o.userData.level === 1 ? 'settlement' : 'city';
        const visuals = [];
        o.traverse(n => { if (n.userData.pieceVisual) visuals.push({ ...n.userData,
          position: n.position.toArray(), rotation: n.rotation.toArray().slice(0, 3), scale: n.scale.toArray() }); });
        result.pieces.push({ kind, id: kind === 'road' ? 'e:' + [...o.userData.edge].sort((a,b)=>a-b).join(',') : 'v:' + o.userData.vertexId,
          owner: o.userData.owner, position: o.position.toArray(), rotation: o.rotation.y, preview: o.userData.preview,
          pose: visuals.find(v => v.pieceVisual === kind) });
      }
      if (o.userData.upgradeEcho && o.visible) result.echoes++;
      if (o.userData.fogReveal && o.visible) result.fog++;
      if (o.userData.shipVisual && o.userData.appearing) result.ships++;
    }); return result;
  });
}
const settled = data => data.pieces.filter(p => !p.preview).every(p => !p.pose?.appearing &&
  (!p.pose || p.pose.scale.every(v => v === 1) && p.pose.position.every(v => v === 0) && p.pose.rotation.every(v => v === 0)));
async function effect(page, kind) {
  await page.waitForFunction(kind => {
    let active = false;
    window.__scene.getState().scene.traverse(o => { active ||= !!o.userData.pieceVisual && o.userData.appearing && o.userData.construction === kind; });
    return active;
  }, kind, { timeout: 4000 });
}
function anchor(piece, state, id) {
  if (id.startsWith('e:')) {
    const edge = state.edges.find(e => [...e].sort((a,b)=>a-b).join(',') === id.slice(2));
    const [a,b] = edge.map(v => state.vertices[v]);
    const expected = [(a[0]+b[0])/state.size/2, .32, (a[1]+b[1])/state.size/2];
    assert(piece.position.every((v,i)=>Math.abs(v-expected[i])<1e-8));
    assert(Math.abs(piece.rotation + Math.atan2(b[1]-a[1],b[0]-a[0]))<1e-8);
  } else {
    const [x,z] = state.vertices[id.slice(2)];
    assert.deepEqual(piece.position, [x/state.size,.26,z/state.size]);
  }
  assert.equal(piece.owner, 0);
}
async function main() {
  await fs.mkdir(output, { recursive: true });
  const demo = await startDemo(0, baseline ? reference : null);
  const browser = await chromium.launch({ channel:'chrome',headless:true });
  const report = { baseline, reference, completed:false, chrome:browser.version(),checks:[],errors:[],screenshots:[] };
  const context = await browser.newContext({ viewport:{width:1440,height:900} });
  await context.addInitScript(observeScene); const page = await context.newPage();
  page.on('pageerror', e=>report.errors.push(e.message));
  page.on('console', m=>{ if(m.type()==='error') report.errors.push(m.text()); });
  const check = text => { report.checks.push(text); console.log('PASS '+text); };
  const shot = async name => { const p=path.join(output,(baseline?'before-':'after-')+name+'.png'); await page.screenshot({path:p});report.screenshots.push(p); };
  const reset = async () => { await page.evaluate(()=>window.__fogFixture.load('partial')); await ready(page); };
  try {
    await page.goto(demo.origin+'/?demo=1&buildings=1'); await ready(page);
    for(const large of [false,true]) {
      await page.evaluate(v=>window.__fogFixture.load(v?'large':'partial'),large); await ready(page);
      await shot(large?'50-hex':'7-hex');
    }
    for(const kind of ['road','settlement','upgrade']) {
      await reset();
      const before = await page.evaluate(()=>window.__fogFixture.snapshot());
      const id = kind==='road' ? 'e:'+before.state.legal.roads[0].join(',')
        : 'v:'+(kind==='settlement'?before.state.legal.settlements[0]:before.state.legal.cities.at(-1));
      if(kind==='road'&&!baseline) await page.evaluate(id=>{
        const f=window.__fogFixture.snapshot(); f.state.edges.find(e=>e.join(',')===id.slice(2)).reverse();
        f.tick++; window.__fogFixture.publish(f);
      },id);
      await page.evaluate(kind=>window.__fogFixture.building(kind),kind);
      if(!baseline) {
        await effect(page,kind); const during=await info(page), piece=during.pieces.find(p=>p.id===id);
        anchor(piece,await page.evaluate(()=>window.__fogFixture.snapshot().state),id);
        assert(piece.pose.appearing && piece.pose.scale.some(v=>v<1));
        if(kind==='road') assert(during.fog>0);
        if(kind==='upgrade') assert.equal(piece.kind,'city');
      }
      await shot(kind+'-during'); await sleep(1100); await shot(kind+'-final');
      if(!baseline) { const current=await info(page);assert(settled(current));assert.equal(current.echoes,0); }
    }
    check('road axis/settlement emergence/distinct city upgrade finish at exact public anchors and owner');
    if(!baseline) {
      let current=await page.evaluate(()=>window.__fogFixture.snapshot());
      await page.evaluate(f=>{window.__fogFixture.publish(f);const old=structuredClone(f);old.tick--;window.__fogFixture.publish(old);window.__fogFixture.reject();},current);
      await sleep(100);assert(settled(await info(page)));assert.deepEqual(await page.evaluate(()=>window.__fogFixture.snapshot()),current);
      check('duplicate/stale/error frames preserve state and do not replay construction');

      await reset(); await page.evaluate(()=>window.__fogFixture.building('road',true));
      await effect(page,'settlement'); assert((await info(page)).pieces.filter(p=>p.pose?.appearing).length>=2);
      await shot('simultaneous');await sleep(1200);assert(settled(await info(page)));
      await reset(); await page.evaluate(()=>{window.__fogFixture.sequence();}); await sleep(300);
      assert((await info(page)).pieces.filter(p=>p.pose?.appearing).length>=2);
      await sleep(1100);assert(settled(await info(page)));assert.equal((await info(page)).echoes,0);
      check('multiple constructions in one frame and rapid road/settlement/city sequence remain finite');

      await reset(); await page.evaluate(()=>window.__fogFixture.building('road'));
      await effect(page,'road'); await page.getByLabel('Construction effects').selectOption('static');await sleep(80);
      assert(settled(await info(page)));await page.getByLabel('Construction effects').selectOption('motion');await sleep(50);assert(settled(await info(page)));
      await reset();await page.emulateMedia({reducedMotion:'reduce'});
      await page.evaluate(()=>window.__fogFixture.building('road',true));await sleep(100);assert(settled(await info(page)));assert.equal(await idleFrames(page),0);
      await page.emulateMedia({reducedMotion:'no-preference'});await sleep(80);assert(settled(await info(page)));
      check('static and reduced motion cancel pending transforms and re-enabling never replays');

      await reset();await page.evaluate(()=>window.__fogFixture.status('disconnected'));await sleep(50);
      await page.evaluate(()=>window.__fogFixture.status('connected'));await sleep(50);
      await page.evaluate(()=>window.__fogFixture.building('settlement'));await sleep(100);assert(settled(await info(page)));
      await page.getByRole('button',{name:'2D',exact:true}).click();await page.evaluate(()=>window.__fogFixture.building('upgrade'));
      await page.getByRole('button',{name:'3D',exact:true}).click();await ready(page);assert(settled(await info(page)));
      await page.reload();await ready(page);assert(settled(await info(page)));
      await reset();assert(settled(await info(page)));
      check('cached reconnect/first fresh frame, SVG switching, hydration and new match stay quiet');

      await page.evaluate(()=>{window.__fogFixture.building('road');window.setTimeout(()=>window.__fogFixture.ship(false),80);});
      await effect(page,'road');await page.waitForFunction(()=>{let s=false;window.__scene.getState().scene.traverse(o=>{s ||= !!o.userData.shipVisual&&o.userData.appearing;});return s;});
      await shot('combined-ships-fog');await sleep(1400);assert(settled(await info(page)));
      const safe=await page.evaluate(()=>{let count=0,ok=true;window.__scene.getState().scene.traverse(o=>{
        if(!o.userData.pieceVisual)return;o.traverse(m=>{if(!m.isMesh)return;count++;const hits=[];try{m.raycast({},hits);ok &&= hits.length===0;}catch{ok=false;}});
      });return {count,ok};});assert(safe.count>0&&safe.ok);
      const commands=await page.evaluate(()=>window.__fogFixture.commands());assert.deepEqual(commands,[]);
      const first=await info(page);await sleep(1000);const later=await info(page);
      assert.equal(later.commits,first.commits);assert.equal(later.geometries,first.geometries);assert.equal(later.textures,first.textures);
      check('combined accepted ship/Fog/road effects preserve targets, pooled resources and idle React stability');
      await page.getByLabel('Fog effects').selectOption('still');await page.getByLabel('Ship effects').selectOption('static');
      await page.getByLabel('Construction effects').selectOption('static');assert.equal(await idleFrames(page),0);
      for(const size of [{width:1024,height:768},{width:1440,height:900}]){
        await page.setViewportSize(size);await sleep(100);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      }
      check('all-still returns to demand idle and desktop resize has no horizontal overflow');

      const vc=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:output,size:{width:1440,height:900}}});
      const vp=await vc.newPage();await vp.goto(demo.origin+'/?demo=1&buildings=1');await sleep(1500);
      await vp.getByRole('button',{name:'Build sequence',exact:true}).click();await sleep(1600);
      await vp.getByRole('button',{name:'Reset preview',exact:true}).click();await sleep(300);
      await vp.getByRole('button',{name:'Build together',exact:true}).click();await sleep(1400);
      const video=vp.video();await vc.close();report.video=await video.path();
    }
    assert.deepEqual(report.errors,[]);report.completed=true;
  }catch(e){report.failure=e.stack;throw e;}
  finally{await fs.writeFile(path.join(output,baseline?'before.json':'after.json'),JSON.stringify(report,null,2));await browser.close();demo.server.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
