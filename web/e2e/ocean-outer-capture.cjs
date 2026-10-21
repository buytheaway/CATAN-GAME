// Supplement an existing gallery with a real-engine legal opening at the outer sea edge.
const assert=require('node:assert/strict');const fs=require('node:fs/promises');const path=require('node:path');const os=require('node:os');
const{chromium}=require('playwright');const{startOcean}=require('./ocean-demo.cjs');const h=require('./ocean-support.cjs');
async function main(){
 const output=path.resolve(process.env.CATAN_OCEAN_OUTPUT||path.join(os.tmpdir(),'catan-ocean-5d2-final-v3'));
 const file=path.join(output,'capture-report.json'),report=JSON.parse(await fs.readFile(file,'utf8'));
 assert(report.completed);assert(!report.captures.some(capture=>capture.scene==='outer-legal'),'Legal outer evidence already exists');
 await fs.writeFile(path.join(output,'capture-report-before-legal-outer.json'),JSON.stringify(report,null,2),{flag:'wx'});
 let demo,browser;const errors=[];
 try{
  demo=await startOcean();browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:2560,height:1440},deviceScaleFactor:1,reducedMotion:'reduce'});await context.addInitScript(h.observeScene);
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const query=h.query('outer-legal');await page.goto(demo.origin+'/preview?'+query);await h.ready(page);
  await page.locator('[data-ocean-preview-toolbar]').evaluate(node=>node.style.visibility='hidden');
  const frame=await page.evaluate(()=>window.__fogFixture.snapshot().state);
  assert.deepEqual(frame.occupied_ships,{'12,17':0});assert.equal(frame.occupied_v['12'][0],0);assert.equal(frame.phase,'setup');
  const anchor=await page.evaluate(()=>{
   const{scene,camera,gl}=window.__scene.getState();let ship;scene.traverse(object=>{if(object.userData.piece==='ship'&&object.userData.edge?.join(',')==='12,17')ship=object;});
   if(!ship)throw Error('Missing actual authoritative ship renderer anchor');
   const point=ship.getWorldPosition(ship.position.clone()).project(camera),rect=gl.domElement.getBoundingClientRect();
   return{x:rect.x+(point.x+1)*rect.width/2,y:rect.y+(1-point.y)*rect.height/2};
  });
  for(const zoom of['normal','detail-legal-outer-ship']){
   const name='outer-legal-after-r1-frame-'+zoom+'.png',clip=zoom==='normal'?null:
    {x:Math.max(0,Math.min(2040,anchor.x-260)),y:Math.max(0,Math.min(1020,anchor.y-210)),width:520,height:420};
   await page.screenshot({path:path.join(output,name),...(clip?{clip}:{})});
   report.captures.push({scene:'outer-legal',source:'after',rings:1,frame:true,zoom,file:name,query,
    detail:'Offline exact NS4 seed17: engine accepted setup settlement vid12 then ship edge12,17. Singleton playable Sea edge, no decorative target. Partial legal opening, not a played network match.',
    sha256:h.hash(await fs.readFile(path.join(output,name))),settings:await h.settings(page),inventory:await h.inventory(page),
    provenance:demo.legalOuter.provenance,bundleHashes:demo.bundleHashes});
  }
  assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);assert.deepEqual(errors,[]);
  report.legalOuter={checkedAt:new Date().toISOString(),...demo.legalOuter.provenance};
  report.checks.push('Offline real-engine NS4 opening: legal settlement12 + ship12,17 on singleton playable Sea; actual renderer exact anchor and public-only two screenshots.');
  await context.close();await fs.writeFile(file,JSON.stringify(report,null,2));
 }finally{if(browser)await browser.close();if(demo)await demo.close();}
 console.log('REPORT '+file);
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
