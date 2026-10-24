const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const{chromium}=require('playwright'),{startProportions,reference}=require('./proportions-demo.cjs');
const h=require('./ocean-support.cjs'),{inventory}=require('./proportions-inventory.cjs');
async function ready(page){await page.waitForFunction(()=>window.__proportionsPreview?.ready||window.__proportionsPreview?.error);assert.equal(await page.evaluate(()=>window.__proportionsPreview.error),undefined);await h.ready(page);}
async function focus(page,kind){return page.evaluate(kind=>{
 const{scene,camera,gl}=window.__scene.getState(),rect=gl.domElement.getBoundingClientRect();let candidates=[];const buildings=[];
 scene.traverse(n=>{if(n.userData.vertexId!=null&&!n.userData.preview)buildings.push(n.getWorldPosition(n.position.clone()));});
 scene.traverse(n=>{const d=n.userData;
  if(d.visibility==='revealed'&&d.terrain===kind)candidates.push(n);
  if(kind==='robber'&&d.piece==='robber')candidates.push(n);
  if(kind==='city'&&d.vertexId!=null&&d.level===2&&!d.preview)candidates.push(n);
  if(kind==='settlement'&&d.vertexId!=null&&d.level===1&&!d.preview)candidates.push(n);
 });
 candidates=candidates.map(n=>{const world=n.getWorldPosition(n.position.clone());world.y+=.3;const projected=world.clone().project(camera);
  const nearBuilding=buildings.some(p=>Math.hypot(p.x-world.x,p.z-world.z)<1.05);
  return{world:world.toArray(),tile:n.userData.tileIndex,vertex:n.userData.vertexId,x:rect.x+(projected.x+1)*rect.width/2,y:rect.y+(1-projected.y)*rect.height/2,
   score:Math.abs(projected.x)+Math.abs(projected.y)+(nearBuilding?0:2)};
 });return candidates.sort((a,b)=>a.score-b.score)[0]||null;
},kind);}
async function main(){const baseline=process.argv.includes('--baseline'),ships=process.argv.includes('--ships'),demo=await startProportions();let browser;
 const report={completed:false,reference,checkedAt:new Date().toISOString(),bundleHashes:demo.bundleHashes,captures:[],inventories:{},errors:[]};
 try{browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
  const cases=ships?['seven']:baseline?['base','four-islands-4']:['base','new-shores-4','four-islands-4','fog-before','fog-after'];
  for(const scene of cases)for(const model of ships?['procedural','glb']:['procedural']){let signature;const cameras={};
   for(const source of baseline?['before']:['before','after']){
    const context=await browser.newContext({viewport:{width:2560,height:1440},deviceScaleFactor:1,reducedMotion:'reduce'});await context.addInitScript(h.observeScene);
    try{const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
     const query=h.query(scene,source,1,true,'static',model)+'&detail=pilot';await page.goto(demo.origin+'/preview?'+query);await ready(page);
     await page.locator('[data-ocean-preview-toolbar]').evaluate(n=>n.style.visibility='hidden');const settings=await h.settings(page);
     if(signature)assert.deepEqual(settings,signature,'identical public state/native camera');else signature=settings;
     report.inventories[[scene,ships?model:'',source].filter(Boolean).join('-')]=await inventory(page);
     if(ships)assert(report.inventories[scene+'-'+model+'-'+source].shipModels.includes(model));
     for(const step of ships?['normal','close']:['normal','close','orbit']){
      if(source==='after')await h.useCamera(page,cameras[step]);else{
       const rect=await page.locator('canvas').boundingBox();
       if(step==='close'){await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);await page.mouse.wheel(0,-500);}
       if(step==='orbit'){await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.5);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.66,rect.y+rect.height*.5,{steps:20});await page.mouse.up();}
       await page.waitForTimeout(150);await page.mouse.move(1,1);cameras[step]=(await h.settings(page)).camera;
      }
      const focuses=step==='normal'||ships?['overview']:['overview',...(scene.startsWith('fog')?['robber']:['fields','pasture','forest','city','settlement',...(scene==='four-islands-4'?['robber']:[])])];
      for(const target of focuses){const point=target==='overview'?null:await focus(page,target);if(target!=='overview'&&!point)continue;
       const clip=point?{x:Math.max(0,Math.min(1960,point.x-300)),y:Math.max(0,Math.min(840,point.y-300)),width:600,height:600}:undefined;
       const file=[scene,ships?model:'',source,step,target].filter(Boolean).join('-')+'.png';await page.screenshot({path:path.join(demo.output,file),...(clip?{clip}:{})});
       report.captures.push({file,scene,source,query,detail:step+' / '+target+(ships?' / '+model:'')+(point?' / native crop':' /2560x1440'),focus:point,camera:cameras[step],sha256:h.hash(await fs.readFile(path.join(demo.output,file)))});
      }
     }
     assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);
    }finally{await context.close();}
   }
  }assert.deepEqual(report.errors,[]);report.completed=true;
 }finally{await browser?.close();await demo.close();await fs.writeFile(path.join(demo.output,'capture-report.json'),JSON.stringify(report,null,2),{flag:'wx'});}
 console.log('CAPTURES '+demo.output+' / '+report.captures.length);
}
module.exports={ready,focus};
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
