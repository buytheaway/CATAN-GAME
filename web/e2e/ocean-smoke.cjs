// Narrow browser invariants for decorative geometry. Synthetic PUBLIC fixtures only.
const assert=require('node:assert/strict');const fs=require('node:fs/promises');const path=require('node:path');const os=require('node:os');
const {chromium}=require('playwright');const {startOcean}=require('./ocean-demo.cjs');const h=require('./ocean-support.cjs');
async function snapshot(page){return page.evaluate(()=>{
 const{scene,gl}=window.__scene.getState(),instances=[];scene.traverse(object=>{
  let parent=object,decoration=false;while(parent){decoration||=!!parent.userData.decorativeOceanHexes;parent=parent.parent;}
  if(decoration&&object.isInstancedMesh)instances.push({uuid:object.uuid,count:object.count,geometry:object.geometry.uuid,
   materials:(Array.isArray(object.material)?object.material:[object.material]).map(material=>material.uuid),matrix:Array.from(object.instanceMatrix.array)});
 });return{instances,geometries:gl.info.memory.geometries,textures:gl.info.memory.textures};
});}
async function rejectionOverlay(page,origin,source){
 await page.goto(origin+'/preview?'+h.query('seven',source));await h.ready(page);
 const rendered=await page.evaluate(()=>window.__scene.getState().gl.info.render.frame);
 await page.getByRole('button',{name:'Ship',exact:true}).click();
 // React selection and the demand-rendered target mesh do not commit inside
 // Playwright's DOM click. Wait for the actual intended edge and a drawn frame.
 await page.waitForFunction(previous=>{
  const store=window.__scene?.getState(),canvas=document.querySelector('canvas');
  if(!store||store.gl.domElement!==canvas||store.gl.info.render.frame<=previous)return false;
  const edge=window.__fogFixture.snapshot().state.legal.ships[0];let found=false;
  store.scene.traverse(n=>{found ||= n.userData.targetType==='edge'&&n.userData.edge.join(',')===edge.join(',');});return found;
 },rendered);
 const target=await page.evaluate(()=>{
  const state=window.__fogFixture.snapshot().state,edge=state.legal.ships[0],{scene,camera,gl}=window.__scene.getState();let mesh;
  scene.traverse(object=>{if(object.userData.targetType==='edge'&&object.userData.edge.join(',')===edge.join(','))mesh=object;});
  if(!mesh)throw Error('Missing existing public legal ship target');
  const point=mesh.getWorldPosition(mesh.position.clone()).project(camera),rect=gl.domElement.getBoundingClientRect();
  return{edge,x:rect.x+(point.x+1)*rect.width/2,y:rect.y+(1-point.y)*rect.height/2};
 });
 if(source==='after'){
  await page.mouse.click(target.x,target.y);await page.waitForFunction(()=>window.__fogFixture.commands().length===1);
  await page.evaluate(()=>window.__fogFixture.settle(false));
 }
 await page.evaluate(()=>window.__fogFixture.reject());await page.getByRole('alert').waitFor();
 // Explicit synthetic occlusion fixture. Alter only the informational alert's
 // rectangle; pointer-events remains the real production CSS under test.
 await page.getByRole('alert').evaluate((node,point)=>Object.assign(node.style,{position:'fixed',transform:'none',
  left:(point.x-90)+'px',top:(point.y-25)+'px',width:'180px',height:'50px',zIndex:'9999'}),target);
 assert(await page.getByRole('alert').isVisible());
 const hit=await page.evaluate(point=>({tag:document.elementFromPoint(point.x,point.y)?.tagName,
  alertPointerEvents:getComputedStyle(document.querySelector('.game-error')).pointerEvents}),target);
 if(source==='before'){
  assert.notEqual(hit.tag,'CANVAS');return{source,...hit,expectedHistoricalBlocking:true};
 }
 assert.equal(hit.tag,'CANVAS','informational rejection must not intercept the legal target');
 assert.equal(hit.alertPointerEvents,'none');await page.mouse.click(target.x,target.y);
 await page.waitForFunction(()=>window.__fogFixture.commands().length===2);
 await page.evaluate(()=>{window.__fogFixture.ship(false);window.__fogFixture.settle(true);});
 await page.waitForFunction(edge=>window.__fogFixture.snapshot().state.occupied_ships[edge.join(',')]===0,target.edge);
 return{source,...hit,commands:2,retryAcceptedBySyntheticPublicFrame:true};
}
async function main(){
 const output=process.env.CATAN_E2E_OUTPUT||path.join(os.tmpdir(),'catan-ocean-smoke-'+Date.now());await fs.mkdir(output,{recursive:true});
 const file=path.join(output,'browser-smoke.json');await fs.writeFile(file,'{}',{flag:'wx'});const report={completed:false,checkedAt:new Date().toISOString(),checks:[],errors:[]};let demo,browser;
 try{
  demo=await startOcean();browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
  const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,reducedMotion:'reduce'});await context.addInitScript(h.observeScene);
  const page=await context.newPage();page.on('pageerror',error=>report.errors.push(error.message));page.on('console',message=>{if(message.type()==='error')report.errors.push(message.text());});
  for(const scene of['base','new-shores-4','fog-before','fifty']){
   await page.goto(demo.origin+'/preview?'+h.query(scene));await h.ready(page);const initial=await snapshot(page);assert(initial.instances.length>=3);
   const positions=await page.evaluate(()=>{
    const{scene,camera,gl}=window.__scene.getState();let tile;scene.traverse(object=>{if(object.userData.terrain&&object.userData.visibility!=='hidden'&&object.userData.tileIndex===0)tile=object;});
    const p=tile.position.clone();tile.getWorldPosition(p);p.y+=.3;p.project(camera);const rect=gl.domElement.getBoundingClientRect();
    return{x:rect.x+(p.x+1)*rect.width/2,y:rect.y+(1-p.y)*rect.height/2};
   });
   await page.mouse.move(positions.x,positions.y);await page.waitForTimeout(100);await page.mouse.move(1,1);await page.waitForTimeout(100);
   assert.deepEqual((await snapshot(page)).instances,initial.instances,'hover must not reconstruct or move ocean instances');
   await page.evaluate(()=>{const frame=window.__fogFixture.snapshot();frame.tick++;window.__fogFixture.publish(frame);});await page.waitForTimeout(150);
   assert.deepEqual((await snapshot(page)).instances,initial.instances,'ordinary snapshot must preserve ocean instances');
   const hit=await page.evaluate(()=>{
    const{scene,camera,raycaster}=window.__scene.getState();scene.updateMatrixWorld(true);let group,mesh;
    scene.traverse(object=>{if(object.userData.decorativeOceanHexes)group=object;if(object.userData.tileIndex===0&&object.isMesh)mesh=object;});
    const matrix=group.children.find(object=>object.userData.decorativeWaterCells).instanceMatrix.array;
    const point=mesh.position.clone().set(matrix[12],.25,matrix[14]).project(camera);
    raycaster.setFromCamera({x:point.x,y:point.y},camera);
    const hits=raycaster.intersectObject(group,true);
    return{hits:hits.length,instances:group.children.filter(object=>object.isInstancedMesh).length};
   });assert.equal(hit.hits,0,'decorative water/frame never intercept raycasts');
   assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);
   const cameraBefore=(await h.settings(page)).camera;
   if(scene==='fog-before'){
    await page.evaluate(()=>window.__fogFixture.reveal(2));await page.waitForTimeout(1800);
    assert.deepEqual((await h.settings(page)).camera,cameraBefore,'public Fog reveal does not change footprint/camera');
    assert.deepEqual((await snapshot(page)).instances,initial.instances,'reveal does not alter decorative geometry');
   }
   assert.equal(await h.idleFrames(page),0);report.checks.push(scene+': hover, ordinary snapshot, raycast pass-through, no commands, stable ocean instances, reduced idle0'+(scene==='fog-before'?', reveal preserves outline/camera':''));
   const stateBeforeControls=await page.evaluate(()=>window.__fogFixture.snapshot()),one=await h.inventory(page);
   await page.getByLabel('Ocean rings',{exact:true}).selectOption('2');
   await page.waitForFunction(()=>document.querySelector('[data-ocean-rings]')?.getAttribute('data-ocean-rings')==='2');
   const two=await h.inventory(page);assert(Number(two.cells)>Number(one.cells));
   const clipping=await h.footprint(page);assert(clipping.framePoints>0&&clipping.allInside,'actual two-ring frame vertices fit overview');
   await page.getByLabel('Ocean frame',{exact:true}).selectOption('0');
   await page.waitForFunction(()=>document.querySelector('[data-ocean-frame]')?.getAttribute('data-ocean-frame')==='false');
   assert(!(await h.inventory(page)).decorativeGroups.some(group=>group.decorativeOceanFrame));
   await page.getByLabel('Ocean rings',{exact:true}).selectOption('0');
   await page.waitForFunction(()=>document.querySelector('[data-ocean-cells]')?.getAttribute('data-ocean-cells')==='0');
   assert.equal((await h.inventory(page)).instancedMeshes,0);
   await page.getByLabel('Ocean rings',{exact:true}).selectOption('1');await page.getByLabel('Ocean frame',{exact:true}).selectOption('1');
   await page.waitForFunction(()=>document.querySelector('[data-ocean-frame]')?.getAttribute('data-ocean-frame')==='true');
   assert.deepEqual(await page.evaluate(()=>window.__fogFixture.snapshot()),stateBeforeControls,'preview controls never mutate public snapshot');
   if(scene==='new-shores-4'){
    const camera=(await h.settings(page)).camera;await page.getByLabel('Ship model',{exact:true}).selectOption('glb');
    await page.waitForFunction(()=>{let count=0,fallback=false;window.__scene.getState().scene.traverse(object=>{count+=object.userData.shipModel==='glb'?1:0;fallback||=!!object.userData.shipAssetFallback;});return count>0&&!fallback;});
    assert.deepEqual((await h.settings(page)).camera,camera,'GLB opt-in does not reframe camera');
    await page.getByLabel('Ship model',{exact:true}).selectOption('procedural');
   }
   report.checks.push(scene+': real 0/1/2 ring and frame controls, actual frame vertices unclipped, snapshot unchanged'+(scene==='new-shores-4'?', GLB opt-in preserves camera':''));
  }
  report.rejectionOverlay=[];
  for(const source of['before','after'])report.rejectionOverlay.push(await rejectionOverlay(page,demo.origin,source));
  report.checks.push('Synthetic forced error-overlay occlusion: historical bundle blocks; current alert remains visible/announced, canvas receives unchanged legal retry; fake ACK/public frame updates occupancy. Actual authority is tested separately by buildings-live.');
  await context.close();assert.deepEqual(report.errors,[]);report.completed=true;
 }catch(error){report.failure=error.stack;throw error;}finally{await fs.writeFile(file,JSON.stringify(report,null,2));if(browser)await browser.close();if(demo)await demo.close();}
 console.log('REPORT '+file);
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
