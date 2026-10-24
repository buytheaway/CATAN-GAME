// Correct asynchronous GPU A/B; no gameplay, fake renderer, video or screenshot during timing.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');const os=require('node:os');const path=require('node:path');
const {chromium}=require('playwright');
const {startOcean,reference}=require('./ocean-demo.cjs');
const {samplePage,summarize,telemetry}=require('./ship-art-gpu.cjs');
const h=require('./ocean-support.cjs');
async function main(options = {}){
 const start = options.start || startOcean, checkpoint = options.reference || reference;
 const query = options.query || h.query;
 const smoke=process.argv.includes('--smoke');
 const output=path.resolve(process.env.CATAN_E2E_OUTPUT||path.join(os.tmpdir(),'catan-ocean-gpu-'+Date.now()));
 await fs.mkdir(output,{recursive:true});const file=path.join(output,'paired-performance.json');await fs.writeFile(file,'{}',{flag:'wx'});
 const report={completed:false,reference:checkpoint,checkedAt:new Date().toISOString(),smoke,errors:[],measurements:{},
  method:{order:[['before','after','after','before'],['after','before','before','after']],
   warmFrames:smoke?5:90,gpuFrames:smoke?4:120,wallFrames:smoke?4:60,
   GPU:'Unchanged ship-art-gpu samplePage: asynchronous TIME_ELAPSED_EXT/disjoint checks; full chronological samples; main and shadows',
   camera:'Working one-ring frame-on overview camera copied identically onto both renderers, native fits also retained',
   ambientBoats:'Native poses and actual main-pass visibility recorded. During GPU probe only, a temporary gl.render wrapper applies the same after-boat poses on both sides, retaining original timer/pose on exit; normal idle measured after restoration.',
   counts:'Same public geometry/occupancy/model, viewport/DPR/light policy; decorative instancing/material inventory recorded separately',
   limits:'Single unlocked GPU; ambient phases evolve; command-span microbenchmark, not sustained FPS or low-end certification'},
  environment:{start:telemetry()}};
 const save=()=>fs.writeFile(file,JSON.stringify(report,null,2));let demo,browser;
 try{
  demo=await start();report.bundleHashes=demo.bundleHashes;browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
  for(const scene of(smoke?['seven']:(options.scenes || ['base','new-shores-4','four-islands-4','seven','fifty'])))for(const mode of(smoke?['static']:['normal','reduced','static'])){
   const key=scene+'-'+mode,result=report.measurements[key]={readings:[],blocks:[]};let canonical,canonicalBoats;
   // Separate unmeasured page determines complete after framing before paired runs.
   const calibration=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,reducedMotion:mode==='reduced'?'reduce':'no-preference'});
   try{await calibration.addInitScript(h.observeScene);const page=await calibration.newPage();
    await page.goto(demo.origin+'/preview?'+query(scene,'after',1,true,mode));await h.ready(page);
    canonical=(await h.settings(page)).camera;result.canonicalCamera=canonical;
    canonicalBoats=await h.boats(page);result.canonicalBoats=canonicalBoats;
   }finally{await calibration.close();}
   for(const[block,order]of report.method.order.entries())for(const[index,side]of order.entries()){
    const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1,reducedMotion:mode==='reduced'?'reduce':'no-preference'});
    try{
     await context.addInitScript(h.observeScene);const page=await context.newPage();
     page.on('pageerror',error=>report.errors.push(error.message));page.on('console',message=>{if(message.type()==='error')report.errors.push(message.text());});
     await page.goto(demo.origin+'/preview?'+query(scene,side,1,true,mode));await h.ready(page);
     const native=await h.settings(page);await h.useCamera(page,canonical);const settings=await h.settings(page);
     const signature={...settings};delete signature.camera;
     if(result.signature)assert.deepEqual(signature,result.signature);else result.signature=signature;
     const nativeBoats=await h.boats(page);await h.normalizeBoats(page,canonicalBoats.poses);
     let measuredBoats,sample;const inventory=await h.inventory(page),beforeTelemetry=telemetry();
     try{measuredBoats=await h.boats(page);sample=await page.evaluate(samplePage,report.method);}
     finally{await h.restoreBoats(page);}
     assert.equal(measuredBoats.actualMainPassVisibleBoats,canonicalBoats.actualMainPassVisibleBoats);
     const reading={block,index,side,native,settings,inventory,nativeBoats,measuredBoats,beforeTelemetry,afterTelemetry:telemetry(),...sample};
     result.readings.push(reading);await save();assert(!sample.failure,sample.failure);
     assert.deepEqual(sample.before,sample.after,'steady render must not allocate/compile');
     assert(sample.gpuSamples.some(value=>!value.disjoint&&Number.isFinite(value.gpuMs)),'No valid GPU timing; raw evidence retained');
     reading.idleFramesPerSecond=await h.idleFrames(page);
     if(mode==='reduced')assert.equal(reading.idleFramesPerSecond,0,'reduced motion returns to demand idle');
     if(mode==='static'&&scene!=='base')assert.equal(reading.idleFramesPerSecond,0,'all existing effects still returns to demand idle');
     assert.deepEqual(await page.evaluate(()=>window.__fogFixture.commands()),[]);await save();
    }finally{await context.close();}
   }
   for(const side of['before','after'])result[side]=summarize(result.readings.filter(reading=>reading.side===side));
   result.idleFrames=Object.fromEntries(['before','after'].map(side=>[side,result.readings.filter(reading=>reading.side===side).map(reading=>reading.idleFramesPerSecond)]));
   assert(Math.max(...result.idleFrames.after)<=Math.max(...result.idleFrames.before)+2,'decorative geometry must not add idle rendering');
   for(const block of[0,1]){const values=Object.fromEntries(['before','after'].map(side=>[side,summarize(result.readings.filter(reading=>reading.block===block&&reading.side===side))]));
    result.blocks.push({block,before:values.before.gpu.median,after:values.after.gpu.median,deltaMs:values.after.gpu.median-values.before.gpu.median});}
   console.log(key+': GPU '+result.before.gpu.median.toFixed(3)+' -> '+result.after.gpu.median.toFixed(3)+' ms; p95 '+result.before.gpu.p95.toFixed(3)+' -> '+result.after.gpu.p95.toFixed(3));await save();
  }
  report.environment.end=telemetry();assert.deepEqual(report.errors,[]);report.completed=true;
 }catch(error){report.failure=error.stack;throw error;}finally{await save();if(browser)await browser.close();if(demo)await demo.close();}
 console.log('REPORT '+file);
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={main};
