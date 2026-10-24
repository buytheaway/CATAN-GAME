// Same async query probe and paired ordering as 5D.2, now against its checkpoint.
const {main}=require('./ocean-gpu.cjs');
const {startReadability,reference}=require('./readability-demo.cjs');
// A separate untimed pass inventory leaves the timing probe unchanged. Actual
// Three callbacks must reconcile with native gl.info calls, not estimated meshes.
async function passes(file, options = {}) {
 const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
 const {chromium}=require('playwright'),h=require('./ocean-support.cjs');
 const measured=JSON.parse(await fs.readFile(file,'utf8')),checkpoint=options.reference||reference,query=options.query||h.query;
 assert(measured.completed);assert.equal(measured.reference,checkpoint);
 const report={completed:false,reference:checkpoint,checkedAt:new Date().toISOString(),cases:{}};
 const demo=await (options.start||startReadability)();let browser;
 try{browser=await chromium.launch({channel:'chrome',headless:true});assert.deepEqual(demo.bundleHashes,measured.bundleHashes);
  for(const[key,value]of Object.entries(measured.measurements)){
   const mode=key.split('-').at(-1),scene=key.slice(0,-mode.length-1);report.cases[key]={};
   for(const side of['before','after']){const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,reducedMotion:mode==='reduced'?'reduce':'no-preference'});
    try{await context.addInitScript(h.observeScene);const page=await context.newPage();await page.goto(demo.origin+'/preview?'+query(scene,side,1,true,mode));await h.ready(page);
     await h.useCamera(page,value.canonicalCamera);await h.normalizeBoats(page,value.canonicalBoats.poses);
     const counts=await page.evaluate(()=>{
      const{scene,camera,gl}=window.__scene.getState(),saved=[],counts={main:0,shadow:0};
      scene.traverse(mesh=>{if(!mesh.isMesh)return;const main=mesh.onBeforeRender,shadow=mesh.onBeforeShadow;
       saved.push([mesh,main,shadow]);mesh.onBeforeRender=function(...args){counts.main++;return main.apply(this,args);};
       mesh.onBeforeShadow=function(...args){counts.shadow++;return shadow.apply(this,args);};});
      const reset=gl.info.autoReset;gl.info.autoReset=false;
      try{gl.info.reset();gl.render(scene,camera);return{...counts,combined:gl.info.render.calls,triangles:gl.info.render.triangles};}
      finally{for(const[mesh,main,shadow]of saved){mesh.onBeforeRender=main;mesh.onBeforeShadow=shadow;}gl.info.autoReset=reset;}
     });
     assert.equal(counts.main+counts.shadow,counts.combined);assert(value[side].calls.includes(counts.combined));assert(value[side].triangles.includes(counts.triangles));
     report.cases[key][side]={...counts,inventory:await h.inventory(page)};
    }finally{await context.close();}
   }
  }report.completed=true;
 }finally{await browser?.close();await demo.close();await fs.writeFile(path.join(path.dirname(file),'pass-inventory.json'),JSON.stringify(report,null,2));}
 console.log('PASS INVENTORY '+path.dirname(file));
}
module.exports={passes};
if(require.main===module){const action=process.argv.includes('--passes')?passes(process.argv.at(-1)):
 main({start:startReadability,reference,scenes:['base','four-islands-4','fifty']});
 action.catch(error=>{console.error(error);process.exitCode=1;});}
