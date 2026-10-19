// Actual Board3D, synthetic authorized display frames only. No hidden recipes or rules.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const { observeScene, ready, idleFrames } = require('./ships-visual.cjs');
const baseline = process.argv.includes('--baseline');
const reference = '93ee22574fd843e87e571e086367374851a47b12';
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(),'catan-threats-visual-phase4');
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function info(page) {
  return page.evaluate(()=>{
    const {scene,gl}=window.__scene.getState();scene.updateMatrixWorld(true);
    const result={figures:[],cards:[],echoes:0,fog:0,ship:0,build:0,frames:gl.info.render.frame,
      geometries:gl.info.memory.geometries,textures:gl.info.memory.textures,commits:window.__sceneCommits};
    scene.traverse(o=>{
      if(o.userData.threatVisual){const m=o.matrixWorld.elements;result.figures.push({...o.userData,
        position:[m[12],m[13],m[14]],local:o.position.toArray(),rotation:o.rotation.toArray().slice(0,3),parentYaw:o.parent.rotation.y});}
      if(o.userData.theftVisual&&o.visible)result.cards.push({data:o.userData,color:o.material.color.getHexString(),
        geometry:o.geometry.type,parameters:o.geometry.parameters,opacity:o.material.opacity});
      if(o.userData.departureVisual&&o.visible)result.echoes++;
      if(o.userData.fogReveal&&o.visible)result.fog++;
      if(o.userData.shipVisual&&o.userData.appearing)result.ship++;
      if(o.userData.pieceVisual&&o.userData.appearing)result.build++;
    });return result;
  });
}
const quiet=d=>d.figures.every(f=>!f.moving&&!f.arriving)&&!d.cards.length&&!d.echoes;
async function ignoresRaycasts(page,category){
  const result=await page.evaluate(category=>{let count=0,safe=true;window.__scene.getState().scene.traverse(o=>{
    if(!o.visible||!o.userData[category])return;
    o.traverse(mesh=>{if(!mesh.isMesh)return;count++;const hits=[];
      try{mesh.raycast({},hits);safe &&= !hits.length;}catch{safe=false;}});
  });return {count,safe};},category);
  assert(result.count>0,category+' must be present during raycast check');assert(result.safe,category+' must not intercept targets');
}
async function effect(page,kind){await page.waitForFunction(kind=>{
  let active=false;window.__scene.getState().scene.traverse(o=>{active ||= o.userData.threatVisual===kind&&(o.userData.moving||o.userData.arriving);});return active;
},kind,{timeout:4000});}
function anchor(figure,state,kind){
  const tile=state.tiles[kind==='robber'?state.robber_tile:state.pirate_tile];
  const [x,z]=tile.center.map(v=>v/state.size),offset=kind==='robber'?[.48,.26,.1]:[.15,.29,.24];
  assert(Math.abs(figure.position[0]-x-offset[0])<1e-8);
  assert(Math.abs(figure.position[2]-z-offset[2])<1e-8);
  assert(Math.abs(figure.position[1]-offset[1])<.005);
  assert.equal(figure.parentYaw,kind==='robber'?0:-.3);
}
async function main(){
  await fs.mkdir(output,{recursive:true});const demo=await startDemo(0,baseline?reference:null);
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const report={baseline,reference,completed:false,chrome:browser.version(),checks:[],errors:[],screenshots:[]};
  const context=await browser.newContext({viewport:{width:1440,height:900}});await context.addInitScript(observeScene);
  const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
  const check=label=>{report.checks.push(label);console.log('PASS '+label);};
  const shot=async name=>{const p=path.join(output,(baseline?'before-':'after-')+name+'.png');await page.screenshot({path:p});report.screenshots.push(p);};
  const reset=async(large=false)=>{await page.evaluate(v=>window.__fogFixture.load(v?'large':'partial'),large);await ready(page);};
  try{
    await page.goto(demo.origin+'/?demo=1&threats=1');await ready(page);
    for(const large of [false,true]){await reset(large);await shot(large?'50-hex':'7-hex');}
    for(const kind of ['robber','pirate']){
      await reset();await page.evaluate(kind=>window.__fogFixture.threat(kind),kind);
      if(!baseline){await effect(page,kind);assert((await info(page)).figures.some(f=>f.threatVisual===kind&&f.moving));}
      await shot(kind+'-during');await sleep(1000);await shot(kind+'-final');
      if(!baseline){const data=await info(page),state=await page.evaluate(()=>window.__fogFixture.snapshot().state);
        assert(quiet(data));anchor(data.figures.find(f=>f.threatVisual===kind),state,kind);}
    }
    if(baseline){check('exact committed Phase3 renderer captured before movement changes');report.completed=true;return;}
    check('adjacent accepted robber/pirate moves lift, arrive and finish at exact public offsets/yaw');

    let signature;
    for(const resource of ['wood','ore']){
      await reset();await page.evaluate(resource=>{
        const f=window.__fogFixture.snapshot();f.tick++;f.state.robber_tile=0;f.state.robbers=[0];
        f.state.game_events=[{id:1,tick:f.tick,at_ms:0,type:'move_robber',actor_pid:0,from_tile:5,tile:0},
          {id:2,tick:f.tick,at_ms:0,type:'theft',actor_pid:0,victim_pid:1,quantity:1,resource}];window.__fogFixture.publish(f);
      },resource);
      await page.waitForFunction(()=>{let n=0;window.__scene.getState().scene.traverse(o=>{if(o.userData.theftVisual&&o.visible)n++;});return n===1;});
      const data=await info(page);assert.equal(data.cards.length,1);if(signature)assert.deepEqual(data.cards[0],signature);else signature=data.cards[0];
      assert(!JSON.stringify(data.cards).includes(resource));await shot('generic-theft-'+resource);await sleep(1000);assert(quiet(await info(page)));
    }
    check('generic theft uses identical neutral geometry/material/public metadata for different authorized resource types');

    await reset();await page.evaluate(()=>{const f=window.__fogFixture.snapshot();f.tick++;
      f.state.robbers=[-1];f.state.robber_tile=-1;window.__fogFixture.publish(f);});
    await page.evaluate(()=>window.__fogFixture.threat('robber',true));
    await page.waitForFunction(()=>{let count=0;window.__scene.getState().scene.traverse(o=>{if(o.userData.theftVisual&&o.visible)count++;});return count===1;});
    let offboard=await info(page);assert.equal(offboard.cards.length,1);assert.equal(offboard.echoes,0);
    assert(offboard.figures.every(f=>!f.moving&&!f.arriving));
    anchor(offboard.figures.find(f=>f.threatVisual==='robber'),await page.evaluate(()=>window.__fogFixture.snapshot().state),'robber');
    await ignoresRaycasts(page,'theftVisual');await shot('offboard-theft-snap');await sleep(800);assert(quiet(await info(page)));
    check('canonical offboard robber snaps; confirmed theft alone shows an identical non-intercepting neutral card');

    await reset(true);await page.evaluate(()=>{
      const f=window.__fogFixture.snapshot();f.tick++;const from=f.state.pirate_tile;f.state.pirate_tile=8;
      f.state.game_events=[{id:1,tick:f.tick,at_ms:0,type:'move_pirate',actor_pid:0,from_tile:from,tile:8}];window.__fogFixture.publish(f);
    });await effect(page,'pirate');
    let data=await info(page);assert.equal(data.echoes,1);const pirate=data.figures.find(f=>f.threatVisual==='pirate');
    assert.equal(pirate.moving,false);assert.equal(pirate.arriving,true);
    await ignoresRaycasts(page,'departureVisual');
    const endpoint=await page.evaluate(()=>window.__fogFixture.snapshot().state.tiles[8].center.map(v=>v/window.__fogFixture.snapshot().state.size));
    assert(Math.abs(pirate.position[0]-endpoint[0]-.15)<1e-8&&Math.abs(pirate.position[2]-endpoint[1]-.24)<1e-8);
    await shot('distant-endpoints');await sleep(1100);assert(quiet(await info(page)));
    await reset();await page.evaluate(()=>{const f=window.__fogFixture.snapshot();f.tick++;f.state.pirate_tile=3;
      f.state.game_events=[{id:1,tick:f.tick,at_ms:0,type:'move_pirate',actor_pid:0,from_tile:1,tile:3}];window.__fogFixture.publish(f);});
    await sleep(100);assert(!(await info(page)).figures.some(f=>f.threatVisual==='pirate'));assert(quiet(await info(page)));
    await reset();await page.evaluate(()=>{const f=window.__fogFixture.snapshot();f.tick++;f.state.robbers=[-1];f.state.robber_tile=-1;window.__fogFixture.publish(f);});
    await page.evaluate(()=>window.__fogFixture.threat('robber'));await sleep(100);assert(quiet(await info(page)));
    check('distant known movement uses endpoints only; hidden/offboard transitions snap without terrain or route invention');

    const committed=await page.evaluate(()=>window.__fogFixture.snapshot());
    await page.evaluate(f=>{window.__fogFixture.publish(f);const old=structuredClone(f);old.tick--;window.__fogFixture.publish(old);window.__fogFixture.reject();},committed);
    await sleep(80);assert(quiet(await info(page)));assert.deepEqual(await page.evaluate(()=>window.__fogFixture.snapshot()),committed);
    await reset();await page.evaluate(()=>{window.__fogFixture.threatSequence();});await sleep(1600);
    data=await info(page);assert(quiet(data));assert.equal(data.figures.length,2);
    const state=await page.evaluate(()=>window.__fogFixture.snapshot().state);for(const figure of data.figures)anchor(figure,state,figure.threatVisual);
    check('duplicate/stale/rejected frames and rapid alternating events cannot replay or leave displaced figures');

    await reset();await page.evaluate(()=>window.__fogFixture.status('disconnected'));await sleep(40);
    await page.evaluate(()=>window.__fogFixture.status('connected'));await sleep(40);
    await page.evaluate(()=>window.__fogFixture.threat('pirate',true));await sleep(100);assert(quiet(await info(page)));
    await page.getByRole('button',{name:'2D',exact:true}).click();await page.evaluate(()=>window.__fogFixture.theft());
    await page.getByRole('button',{name:'3D',exact:true}).click();await ready(page);assert(quiet(await info(page)));
    await page.reload();await ready(page);assert(quiet(await info(page)));await reset();assert(quiet(await info(page)));
    check('first fresh reconnect, SVG switching, refresh and new epoch never replay movement or theft');

    await page.evaluate(()=>window.__fogFixture.threat('robber',true));await effect(page,'robber');
    await page.getByLabel('Robber & pirate effects').selectOption('static');await sleep(80);assert(quiet(await info(page)));
    await page.getByLabel('Robber & pirate effects').selectOption('motion');await sleep(80);assert(quiet(await info(page)));
    await reset();await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>window.__fogFixture.theft());
    await sleep(100);assert(quiet(await info(page)));assert.equal(await idleFrames(page),0);await shot('reduced');
    await page.emulateMedia({reducedMotion:'no-preference'});await sleep(80);assert(quiet(await info(page)));
    check('static/reduced immediately restore final pieces, suppress theft and never replay on re-enable');

    await reset();await page.evaluate(()=>{window.__fogFixture.building('road');window.setTimeout(()=>window.__fogFixture.ship(false),50);
      window.setTimeout(()=>window.__fogFixture.threat('pirate',true),100);});
    await effect(page,'pirate');data=await info(page);assert(data.build>0||data.ship>0);assert(data.cards.length===1);
    await ignoresRaycasts(page,'theftVisual');await ignoresRaycasts(page,'threatVisual');
    await shot('combined');await sleep(1300);assert(quiet(await info(page)));
    assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);
    await page.getByLabel('Fog effects').selectOption('still');await page.getByLabel('Ship effects').selectOption('static');
    await page.getByLabel('Construction effects').selectOption('static');await page.getByLabel('Robber & pirate effects').selectOption('static');
    assert.equal(await idleFrames(page),0);
    for(const size of [{width:1024,height:768},{width:1440,height:900}]){await page.setViewportSize(size);await sleep(100);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
    check('combined Fog/ship/building effects remain clickable, finite, all-still idle and desktop layout safe');

    const vc=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:output,size:{width:1440,height:900}}});
    const vp=await vc.newPage();await vp.goto(demo.origin+'/?demo=1&threats=1');await sleep(1500);
    await vp.getByRole('button',{name:'Move robber',exact:true}).click();await sleep(1000);
    await vp.getByRole('button',{name:'Move pirate',exact:true}).click();await sleep(1000);
    await vp.getByRole('button',{name:'Generic theft',exact:true}).click();await sleep(1000);
    await vp.getByRole('button',{name:'Movement sequence',exact:true}).click();await sleep(1800);
    const video=vp.video();await vc.close();report.video=await video.path();
    assert.deepEqual(report.errors,[]);report.completed=true;
  }catch(e){report.failure=e.stack;throw e;}
  finally{await fs.writeFile(path.join(output,baseline?'before.json':'after.json'),JSON.stringify(report,null,2));await browser.close();demo.server.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
