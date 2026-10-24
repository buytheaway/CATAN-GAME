const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const{chromium}=require('playwright'),{startProportions,reference}=require('./proportions-demo.cjs');
const h=require('./ocean-support.cjs'),{ready}=require('./proportions-capture.cjs');
const{inspect,tileAt,hiddenVegetation,token,anchor}=require('./readability-smoke.cjs');
async function shapes(page){return page.evaluate(()=>{const rows=[];window.__scene.getState().scene.traverse(n=>{
 if(n.name.startsWith('Hex_'))rows.push({name:n.name,position:n.position.toArray(),scale:n.scale.toArray(),visible:n.visible});
});return rows;});}
async function main(){const output=process.env.CATAN_E2E_OUTPUT||path.join(os.tmpdir(),'catan-proportions-smoke-'+Date.now());await fs.mkdir(output,{recursive:true});
 const file=path.join(output,'browser-smoke.json');await fs.writeFile(file,'{}',{flag:'wx'});
 const report={completed:false,reference,checkedAt:new Date().toISOString(),checks:[],errors:[],idle:{},screenshots:[]};let demo,browser;
 const check=text=>{report.checks.push(text);console.log('PASS '+text);};
 try{demo=await startProportions();report.bundleHashes=demo.bundleHashes;browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
  async function open(scene='four-islands-4',detail='pilot',mode='static',source='after',fixture='shipsart'){
   const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,reducedMotion:mode==='reduced'?'reduce':'no-preference'});
   await context.addInitScript(h.observeScene);const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
   const query=new URLSearchParams(h.query(scene,source,1,true,mode));query.set('detail',detail);
   if(fixture!=='shipsart'){query.delete('shipsart');query.set(fixture,'1');}
   await page.goto(demo.origin+'/preview?'+query);await ready(page);return page;
  }
  const old=await open('four-islands-4','current','static','before'),current=await open('four-islands-4','current');
  assert.deepEqual(await shapes(current),await shapes(old),'production current is the committed visual geometry');
  assert.deepEqual((await inspect(current)).tiles,(await inspect(old)).tiles);await old.context().close();await current.context().close();
  check('production/default current matches committed5E.1 transforms, visibility, tokens and public hit geometry');

  const toggled=await open('base','pilot');const pilot=await shapes(toggled),camera=(await h.settings(toggled)).camera;
  await toggled.getByLabel('Terrain detail proposal').selectOption('current');await toggled.waitForTimeout(100);
  assert.notDeepEqual(await shapes(toggled),pilot);assert.deepEqual((await h.settings(toggled)).camera,camera);
  await toggled.getByLabel('Terrain detail proposal').selectOption('pilot');await toggled.waitForTimeout(100);
  assert.deepEqual(await shapes(toggled),pilot);assert.deepEqual((await h.settings(toggled)).camera,camera);await toggled.context().close();
  check('live opt-in/current comparison restores clone proportions while preserving camera and public state');

  const page=await open();const state=await page.evaluate(()=>window.__fogFixture.snapshot()),data=await inspect(page);
  assert.equal(state.state.robber_tile,29);assert.equal(state.state.tiles[29].number,12);token(tileAt(data,29),-.2);anchor(data,state.state,29);
  for(const name of ['Hex_Fields_Wheat_Fringe_01','Hex_Fields_Wheat_Mass_03','Hex_Fields_Wheat_Mass_04','Hex_Fields_Wheat_Mass_05'])assert(hiddenVegetation(tileAt(data,29)).includes(name));
  assert(data.tiles.every(t=>t.terrainRaycasts));const originalState=JSON.stringify(state);
  await page.locator('canvas').click({position:{x:450,y:300}});assert.equal(JSON.stringify(await page.evaluate(()=>window.__fogFixture.snapshot())),originalState);assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);
  check('pilot retains Fields12/tile29 standing clearance, exact robber anchor, token value/offset and non-intercepting decorations');
  await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForSelector('[data-renderer="2d"] svg');
  assert.equal(JSON.stringify(await page.evaluate(()=>window.__fogFixture.snapshot())),originalState);
  await page.getByRole('button',{name:'3D',exact:true}).click();await page.waitForFunction(()=>window.__scene?.getState().gl.domElement===document.querySelector('canvas'));await ready(page);anchor(await inspect(page),state.state,29);
  check('SVG switch and return retain authoritative state and restored public Board3D geometry');
  await page.context().close();

  for(const mode of ['normal','reduced','static']){
   const p=await open('four-islands-4','pilot',mode);report.idle[mode]=await h.idleFrames(p);if(mode!=='normal')assert.equal(report.idle[mode],0);else assert(report.idle[mode]<=20);
   const file=path.join(output,'fi4-'+mode+'.png');await p.screenshot({path:file});report.screenshots.push(file);await p.context().close();
  }check('normal/reduced/static retain bounded existing motion and zero reduced/static idle frames');

  const fog=await open('fog-before','pilot','normal');const hidden=await inspect(fog);
  for(const t of hidden.tiles.filter(t=>t.visibility==='hidden'))assert.equal(t.assets.length+t.tokens.length+t.vegetation.length,0);
  const fogCamera=(await h.settings(fog)).camera;
  await fog.evaluate(()=>{const f=window.__fogFixture.snapshot();f.tick++;const tile=f.state.tiles.find(t=>t.visibility==='hidden');tile.visibility='revealed';tile.terrain='pasture';tile.number=8;f.state.game_events=[];window.__fogFixture.publish(f);});
  await h.ready(fog);assert.deepEqual((await h.settings(fog)).camera,fogCamera,'reveal does not reset framing');
  const revealed=await shapes(fog);assert(revealed.some(n=>n.name==='Hex_Pasture_Sheep_01_Alert'&&n.scale[0]<1));
  await fog.context().close();check('hidden Fog constructs no private terrain or token; public reveal gets pilot decoration without camera reset');

  const play=await open('seven','pilot','normal');
  await play.getByRole('button',{name:'Ship',exact:true}).click();
  const point=await play.evaluate(()=>{const s=window.__fogFixture.snapshot().state,e=s.legal.ships[0],{scene,camera,gl}=window.__scene.getState();let target;scene.traverse(n=>{if(n.userData.targetType==='edge'&&n.userData.edge.join(',')===e.join(','))target=n;});if(!target)throw Error('Missing existing ship legal target');const p=target.getWorldPosition(target.position.clone()).project(camera),r=gl.domElement.getBoundingClientRect();return{x:r.x+(p.x+1)*r.width/2,y:r.y+(1-p.y)*r.height/2};});
  await play.mouse.click(point.x,point.y);await play.waitForFunction(()=>window.__fogFixture.commands().length===1);
  await play.evaluate(()=>{window.__fogFixture.ship(false);window.__fogFixture.settle(true);});
  await play.reload();await ready(play);
  const route=await play.evaluate(()=>{const state=window.__fogFixture.snapshot().state;return{from:state.legal.move_ship.sources[0].join(','),to:state.legal.ships[0].join(',')};});
  await play.evaluate(()=>window.__fogFixture.ship(true));await play.waitForTimeout(1000);
  assert(await play.evaluate(({from,to})=>{const occupied=window.__fogFixture.snapshot().state.occupied_ships;return !(from in occupied)&&occupied[to]===0;},route));
  await play.evaluate(()=>window.__fogFixture.threat('robber'));await play.waitForTimeout(1000);
  const moved=await inspect(play);anchor(moved,(await play.evaluate(()=>window.__fogFixture.snapshot())).state,(await play.evaluate(()=>window.__fogFixture.snapshot())).state.robber_tile);
  await play.evaluate(()=>window.__fogFixture.threat('pirate'));await play.waitForTimeout(1000);
  await play.evaluate(()=>window.__fogFixture.status('disconnected'));await play.waitForTimeout(40);
  await play.evaluate(()=>window.__fogFixture.status('connected'));await play.waitForTimeout(40);
  await play.evaluate(()=>window.__fogFixture.threat('robber'));await play.waitForTimeout(100);
  const final=await inspect(play);assert(final.figures.every(f=>!f.moving&&!f.arriving));
  await play.reload();await ready(play);assert((await inspect(play)).figures.every(f=>!f.moving&&!f.arriving));
  await play.getByLabel('Ship model',{exact:true}).selectOption('glb');
  await play.waitForFunction(()=>{let glb=0,fallback=0;window.__scene.getState().scene.traverse(n=>{if(n.userData.shipModel==='glb')glb++;if(n.userData.shipAssetFallback)fallback++;});return glb>0&&fallback===0;});
  await play.getByLabel('Ship model',{exact:true}).selectOption('procedural');
  await play.context().close();check('actual legal ship pointer/controller, confirmed ship/threat frames, opt-in GLB and reconnect/reload keep final anchors without replay');

  const build=await open('seven','pilot','normal','after','buildings');
  await build.evaluate(()=>{const frame=window.__fogFixture.snapshot();frame.tick++;frame.state.tiles[0].terrain='fields';frame.state.tiles[2].terrain='pasture';window.__fogFixture.publish(frame);});await h.ready(build);
  assert(await build.evaluate(()=>{let transformed=false;window.__scene.getState().scene.traverse(n=>{if(n.name==='Hex_Fields_Wheat_Mass_01'&&n.scale.y<1)transformed=true;});return transformed;}));
  for(const kind of ['road','settlement','upgrade']){
   const prior=await build.evaluate(()=>window.__fogFixture.snapshot());await build.evaluate(kind=>window.__fogFixture.building(kind),kind);
   await build.waitForFunction(tick=>window.__fogFixture.snapshot().tick>tick,prior.tick);await build.waitForTimeout(850);
  }
  assert(await build.evaluate(()=>Object.values(window.__fogFixture.snapshot().state.occupied_v).some(([owner,level])=>owner===0&&level===2)));
  await build.context().close();check('existing public construction fixture on synthetic Fields/Pasture confirms road, settlement and city upgrade with unchanged ownership and finite effects');
  assert.deepEqual(report.errors,[]);report.completed=true;
 }finally{await browser?.close();await demo?.close();await fs.writeFile(file,JSON.stringify(report,null,2));}
 console.log('SMOKE '+output);
}
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
