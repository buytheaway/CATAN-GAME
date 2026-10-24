const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const{chromium}=require('playwright'),{startProportions,reference}=require('./proportions-demo.cjs');
const h=require('./ocean-support.cjs');
// Exact transformed vertex bounds, not Blender source dimensions or a guessed
// silhouette percentage. Screen bounds are projected geometry, not visible pixels.
async function inventory(page){return page.evaluate(()=>{
 const{scene,camera,gl}=window.__scene.getState();scene.updateMatrixWorld(true);camera.updateMatrixWorld();
 const rect=gl.domElement.getBoundingClientRect(),rows=[];
 const visible=node=>{for(let p=node;p;p=p.parent)if(!p.visible)return false;return true;};
 function measure(root,frame=root){
  const inverse=frame.matrixWorld.clone().invert(),min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  const screenMin=[Infinity,Infinity],screenMax=[-Infinity,-Infinity];let triangles=0,meshes=0;
  root.traverse(mesh=>{if(!mesh.isMesh||mesh.isInstancedMesh||!visible(mesh))return;
   const attr=mesh.geometry.getAttribute('position');if(!attr)return;meshes++;
   triangles+=(mesh.geometry.index?.count||attr.count)/3;
   const point=mesh.position.clone();
   for(let i=0;i<attr.count;i++){
    point.set(attr.getX(i),attr.getY(i),attr.getZ(i)).applyMatrix4(mesh.matrixWorld);
    const local=point.clone().applyMatrix4(inverse).toArray();for(let j=0;j<3;j++){min[j]=Math.min(min[j],local[j]);max[j]=Math.max(max[j],local[j]);}
    point.project(camera);const pixel=[(point.x+1)*rect.width/2,(1-point.y)*rect.height/2];
    for(let j=0;j<2;j++){screenMin[j]=Math.min(screenMin[j],pixel[j]);screenMax[j]=Math.max(screenMax[j],pixel[j]);}
   }
  });
  return meshes?{min,max,size:max.map((v,i)=>v-min[i]),triangles,meshes,projectedPixels:screenMax.map((v,i)=>v-screenMin[i])}:null;
 }
 const terrainSeen=new Set(),pieceSeen=new Set(),shipModels=new Set();
 scene.traverse(root=>{
  const d=root.userData;
  if(d.shipModel)shipModels.add(d.shipModel);
  if(d.decorativeOceanFrame)rows.push({category:'envelope',kind:'frame',...measure(root,scene)});
  if(d.decorativeWaterCells&&root.isInstancedMesh){
   const p=root.geometry.getAttribute('position'),min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
   for(let i=0;i<p.count;i++)for(let axis=0;axis<3;axis++){const value=[p.getX(i),p.getY(i),p.getZ(i)][axis];min[axis]=Math.min(min[axis],value);max[axis]=Math.max(max[axis],value);}
   rows.push({category:'envelope',kind:'decorative-water-cell',min,max,size:max.map((v,i)=>v-min[i]),cellCount:root.count,
    trianglesPerCell:(root.geometry.index?.count||p.count)/3,units:'one existing unit-scale instance, not the complete board'});
  }
  if(d.visibility==='revealed'&&d.terrain&&!terrainSeen.has(d.terrain)){
   const state=window.__fogFixture.snapshot().state;if((state.robbers||[state.robber_tile]).includes(d.tileIndex))return;
   terrainSeen.add(d.terrain);const parts=[];let asset;
   root.traverse(part=>{if(part.userData.terrainAsset)asset=part;
    if(/^Hex_(?:Pasture_Sheep_\d+_(?:Alert|Looking_Aside|Grazing|Standing|Lamb)|Fields_Wheat_(?:Mass|Fringe)_\d+|Forest_Pine_\d+)$/.test(part.name))
     parts.push({name:part.name,position:part.position.toArray(),...measure(part,root)});});
   rows.push({category:'terrain',kind:d.terrain,tile:d.tileIndex,...measure(asset||root,root),parts});
  }
  let kind=d.piece|| (d.vertexId!=null?(d.level===2?'city':'settlement'):null);
  if(d.pieceAsset||d.number!=null&&!d.visibility||d.portReadout)kind=d.pieceAsset|| (d.number!=null?'number-token':'port-readout');
  if(kind&&!d.preview&&!pieceSeen.has(kind)&&visible(root)){pieceSeen.add(kind);rows.push({category:'piece',kind,...measure(root)});}
 });
 return{rows,shipModels:[...shipModels],camera:{position:camera.position.toArray(),fov:camera.fov},viewport:[rect.width,rect.height],
  contract:{hexAcrossFlats:Math.sqrt(3),hexAcrossCorners:2,hexArea:3*Math.sqrt(3)/2,units:'Three world units; tile radius1',projection:'geometry bounding rectangle; not a segmented visible silhouette'}};
});}
async function main(){const demo=await startProportions();let browser;
 const report={completed:false,reference,checkedAt:new Date().toISOString(),bundleHashes:demo.bundleHashes,scenes:{},errors:[]};
 try{browser=await chromium.launch({channel:'chrome',headless:true});report.chrome=browser.version();
  for(const scene of['base','new-shores-4','four-islands-4','seven','fifty'])for(const model of['procedural','glb']){
   const context=await browser.newContext({viewport:{width:2560,height:1440},deviceScaleFactor:1,reducedMotion:'reduce'});
   try{await context.addInitScript(h.observeScene);const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
    await page.goto(demo.origin+'/preview?'+h.query(scene,'before',1,true,'static',model));await h.ready(page);
    report.scenes[scene+'-'+model]=await inventory(page);
    if(scene!=='base')assert(report.scenes[scene+'-'+model].shipModels.includes(model),'requested ship model actually loaded');
   }finally{await context.close();}
  }assert.deepEqual(report.errors,[]);report.completed=true;
 }finally{await browser?.close();await demo.close();await fs.writeFile(path.join(demo.output,process.env.CATAN_PROPORTIONS_INVENTORY_FILE||'baseline-inventory.json'),JSON.stringify(report,null,2),{flag:'wx'});}
 console.log('BASELINE INVENTORY '+demo.output);
}
module.exports={inventory};
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
