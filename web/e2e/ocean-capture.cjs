// Actual current and committed Board3D captures; all PNGs remain outside Git.
const assert=require('node:assert/strict');const fs=require('node:fs/promises');const path=require('node:path');const os=require('node:os');
const {execFileSync}=require('node:child_process');const {chromium}=require('playwright');
const {startOcean,reference}=require('./ocean-demo.cjs');const h=require('./ocean-support.cjs');
async function main(){
 const output=path.resolve(process.env.CATAN_OCEAN_OUTPUT||path.join(os.tmpdir(),'catan-ocean-5d2'));await fs.mkdir(output,{recursive:true});
 const file=path.join(output,'capture-report.json');await fs.writeFile(file,'{}',{flag:'wx'});
 const report={completed:false,reference,head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),checkedAt:new Date().toISOString(),
  method:'Real GamePage/Board3D, synthetic PUBLIC snapshots. Native overview, shared after overview for matched A/B, actual wheel close, native-pixel detail crops. Reduced motion, no gameplay/secret assignments.',
  viewport:{width:2560,height:1440,deviceScaleFactor:1},captures:[],checks:[],errors:[],assetResponses:[]};
 const save=()=>fs.writeFile(file,JSON.stringify(report,null,2));let demo,browser;
 try{
  demo=await startOcean();report.bundleHashes=demo.bundleHashes;browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
  report.boards=Object.fromEntries(Object.entries(demo.boards).map(([id,board])=>[id,{map:board.map_id,tiles:board.tiles.length,ports:board.ports.length,hash:h.hash(board)}]));
  const context=await browser.newContext({viewport:{width:2560,height:1440},deviceScaleFactor:1,reducedMotion:'reduce'});await context.addInitScript(h.observeScene);
  const sceneList=process.argv.includes('--smoke')?['base']:['base','new-shores-3','new-shores-4','four-islands-3','four-islands-4','fog-before','fog-after'];
  for(const scene of sceneList){
   let canonical,stateHash;
   for(const variant of[{source:'after',rings:1,frame:true,zoom:'normal'},{source:'before',rings:0,frame:false,zoom:'normal'},
    {source:'before',rings:0,frame:false,zoom:'matched'},{source:'after',rings:2,frame:true,zoom:'normal'},
    {source:'after',rings:1,frame:false,zoom:'normal'}]){
    const page=await context.newPage();page.on('pageerror',error=>report.errors.push(error.message));page.on('console',message=>{if(message.type()==='error')report.errors.push(message.text());});
    page.on('response',response=>{if(response.url().includes('/models/'))report.assetResponses.push({scene,status:response.status(),path:new URL(response.url()).pathname});});
    try{
     const query=h.query(scene,variant.source,variant.rings,variant.frame);await page.goto(demo.origin+'/preview?'+query);await h.ready(page);
     const native=await h.settings(page);if(!stateHash)stateHash=native.publicStateHash;else assert.equal(native.publicStateHash,stateHash,'public board must be identical across views');
     if(variant.source==='after'&&variant.rings===1&&variant.frame)canonical=native.camera;
     if(variant.zoom==='matched')await h.useCamera(page,canonical);
     await page.locator('[data-ocean-preview-toolbar]').evaluate(node=>node.style.visibility='hidden');
     const take=async(zoom,detail='',clip)=>{
      const name=[scene,variant.source,'r'+variant.rings,variant.frame?'frame':'open',zoom].join('-')+'.png';
      const frameClipping=await h.footprint(page);
      if(variant.source==='after'&&variant.frame&&!clip&&zoom!=='close')assert(frameClipping.framePoints>0&&frameClipping.allInside,'actual frame vertices must fit overview');
      await page.screenshot({path:path.join(output,name),...(clip?{clip}:{})});
      report.captures.push({scene,source:variant.source,rings:variant.rings,frame:variant.frame,zoom,detail,file:name,query,
       sha256:h.hash(await fs.readFile(path.join(output,name))),frameClipping,native,settings:await h.settings(page),inventory:await h.inventory(page)});await save();
     };
     await take(variant.zoom,variant.zoom==='matched'?'Exact same after/full-frame camera as the after one-ring normal capture.':'Native current auto-fit; before and after camera framing are recorded separately.');
     if(variant.frame&&variant.rings===1&&variant.source==='after'){
      // Camera reset, viewport resize and SVG round-trip use actual production controls.
      const rect=await page.locator('canvas').boundingBox();await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);
      await page.mouse.wheel(0,-600);await page.waitForTimeout(250);await page.mouse.move(1,1);await take('close','Real wheel zoom; close view intentionally crops.');
      await page.getByRole('button',{name:'Reset Camera',exact:true}).click();await page.waitForTimeout(150);
      const reset=await h.settings(page);assert.deepEqual(reset.camera,native.camera,'reset restores native overview');
      await page.setViewportSize({width:1440,height:900});await page.waitForTimeout(200);assert(await page.locator('canvas').isVisible());
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'canvas must not create horizontal scrolling');
      await page.setViewportSize({width:2560,height:1440});await page.waitForTimeout(200);
      const original=await page.evaluate(()=>window.__fogFixture.snapshot());
      await page.getByRole('button',{name:'2D',exact:true}).click();await page.waitForSelector('[data-renderer="2d"] svg');assert.equal(await page.locator('canvas').count(),0);
      assert.deepEqual(await page.evaluate(()=>window.__fogFixture.snapshot()),original);
      await page.getByRole('button',{name:'3D',exact:true}).click();await h.ready(page);assert.deepEqual(await page.evaluate(()=>window.__fogFixture.snapshot()),original);
      assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);assert.equal(await h.idleFrames(page),0);
      report.checks.push(scene+': zoom/reset, resize/no-scroll, SVG round-trip, same state, no commands, reduced idle0');
      if(scene==='new-shores-4'){
       // Native pixel crops at real public coordinates, not generated or upscaled imagery.
       const anchors=await page.evaluate(()=>{
        const state=window.__fogFixture.snapshot().state,{camera,gl}=window.__scene.getState(),canvas=gl.domElement.getBoundingClientRect();
        const toScreen=point=>{const p=camera.position.clone().set(point[0]/state.size,.35,point[1]/state.size).project(camera);
          return{x:canvas.x+(p.x+1)*canvas.width/2,y:canvas.y+(1-p.y)*canvas.height/2};};
        const midpoint=edge=>edge.map(v=>state.vertices[v]).reduce((a,b)=>[a[0]+b[0]/2,a[1]+b[1]/2],[0,0]);
        const coast=state.edges.find(edge=>{const tiles=state.edge_adj_hexes[edge.join(',')];return tiles.length===2&&tiles.some(i=>state.tiles[i].terrain==='sea')&&tiles.some(i=>state.tiles[i].terrain!=='sea');});
        const outer=Object.keys(state.occupied_ships).find(key=>state.edge_adj_hexes[key].length===1);
        return{coast:toScreen(midpoint(coast)),port:toScreen(midpoint(state.ports[0][0])),pirate:toScreen(state.tiles[state.pirate_tile].center),
          'outer-playable-ship':toScreen(midpoint((outer||Object.keys(state.occupied_ships)[0]).split(',').map(Number)))};
       });
       for(const[name,p]of Object.entries(anchors)){
        const clip={x:Math.max(0,Math.min(2560-520,p.x-260)),y:Math.max(0,Math.min(1440-420,p.y-210)),width:520,height:420};
        await take('detail-'+name,'Native pixel browser crop. Public synthetic display; outer ship uses existing playable edge, not a legal match proof.',clip);
       }
       const corner=await h.frameCorner(page);
       if(corner)await take('detail-frame-corner','Native pixel corner crop from the actual continuous perimeter.',{x:Math.max(0,Math.min(2040,corner.x-260)),y:Math.max(0,Math.min(1020,corner.y-210)),width:520,height:420});
      }
     }
    }finally{await page.close();}
   }
   console.log('CAPTURE '+scene);await save();
  }
  await context.close();assert.deepEqual(report.errors,[]);assert(report.assetResponses.every(response=>response.status===200));report.completed=true;
 }catch(error){report.failure=error.stack;throw error;}finally{await save();if(browser)await browser.close();if(demo)await demo.close();}
 console.log('REPORT '+file);
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
