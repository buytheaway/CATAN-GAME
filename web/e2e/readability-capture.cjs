const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('playwright');
const {startReadability,reference}=require('./readability-demo.cjs');
const h=require('./ocean-support.cjs');
async function ready(page){await page.waitForFunction(()=>window.__readabilityPreview?.ready||window.__readabilityPreview?.error);assert.equal(await page.evaluate(()=>window.__readabilityPreview.error),undefined);await h.ready(page);}
async function figure(page){return page.evaluate(()=>{
 const {scene,camera,gl}=window.__scene.getState();let root;scene.traverse(n=>{if(n.userData.piece==='robber')root=n;});
 if(!root)return null;const world=root.getWorldPosition(root.position.clone()),p=world.clone().project(camera),r=gl.domElement.getBoundingClientRect();
 return{tile:root.userData.tileIndex,world:world.toArray(),x:r.x+(p.x+1)*r.width/2,y:r.y+(1-p.y)*r.height/2};
});}
async function main(){const demo=await startReadability();let browser;
 const report={completed:false,reference,checkedAt:new Date().toISOString(),bundleHashes:demo.bundleHashes,captures:[],cases:[],errors:[]};
 try{browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
 const cases=[['four-islands-4','',true],['base','',false],['new-shores-4','',false],
  ...['forest','pasture','hills','mountains'].map(t=>['four-islands-4',t,true]),['base','desert',true],['fog-after','gold',true],['fog-before','',false]];
 for(const[scene,terrain,detail]of cases){
  const context=await browser.newContext({viewport:{width:2560,height:1440},deviceScaleFactor:1,reducedMotion:'reduce'});await context.addInitScript(h.observeScene);
  let signature,cameras={};
  try{for(const source of ['before','after']){const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
   const query=h.query(scene,source)+(terrain?'&terrain='+terrain:'');await page.goto(demo.origin+'/preview?'+query);await ready(page);
   await page.locator('[data-ocean-preview-toolbar]').evaluate(n=>n.style.visibility='hidden');const settings=await h.settings(page);
   if(signature)assert.deepEqual(settings,signature,'public state, native camera and projection identical');else signature=settings;
   const steps=scene==='four-islands-4'&&!terrain?['normal','close','orbit-left','orbit-back','orbit-right']:['normal'];
   for(const step of steps){
    if(source==='after')await h.useCamera(page,cameras[step]);else{
     const rect=await page.locator('canvas').boundingBox();
     if(step==='close'){await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);await page.mouse.wheel(0,-600);}
     else if(step.startsWith('orbit')){await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.55);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.75,rect.y+rect.height*.55,{steps:20});await page.mouse.up();}
     await page.waitForTimeout(150);await page.mouse.move(1,1);cameras[step]=(await h.settings(page)).camera;
    }
    const anchor=await figure(page);const name=[scene,terrain,source,step].filter(Boolean).join('-');
    for(const crop of detail?[false,true]:[false]){const file=name+(crop?'-detail':'')+'.png';
     const clip=crop&&anchor?{x:Math.max(0,Math.min(2040,anchor.x-260)),y:Math.max(0,Math.min(960,anchor.y-300)),width:520,height:480}:undefined;
     await page.screenshot({path:path.join(demo.output,file),...(clip?{clip}:{})});
     report.captures.push({file,scene,source,query,detail:[terrain||'original',step,crop?'native pixel crop':'2560x1440'].join(' / '),anchor,camera:cameras[step],sha256:h.hash(await fs.readFile(path.join(demo.output,file)))});
    }
   }
   const data=await page.evaluate(()=>{const{scene}=window.__scene.getState();const tiles=[];scene.traverse(n=>{if(n.userData.tileIndex==null||!n.userData.terrain)return;const hidden=[];n.traverse(c=>{if(c.name.startsWith('Hex_')&&!c.visible)hidden.push(c.name);});tiles.push({id:n.userData.tileIndex,hidden});});return{tiles,commands:window.__fogFixture.commands()};});
   assert.deepEqual(data.commands,[]);report.cases.push({scene,terrain,source,settings,data});await page.close();
  }}finally{await context.close();}
 }
 assert.deepEqual(report.errors,[]);report.completed=true;
 }catch(error){report.failure=error.stack;throw error;}finally{await fs.writeFile(path.join(demo.output,'capture-report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();await demo.close();}
 console.log('REPORT '+demo.output+' / '+report.captures.length+' screenshots');
}
module.exports={ready,figure};
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
