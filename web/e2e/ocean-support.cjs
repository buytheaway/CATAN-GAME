const assert = require('node:assert/strict');
const {createHash}=require('node:crypto');
const {fullyReady,sceneSettings}=require('./buildings-compare.cjs');
const {observeScene,idleFrames}=require('./ships-visual.cjs');
const hash=value=>createHash('sha256').update(typeof value==='string'||Buffer.isBuffer(value)?value:JSON.stringify(value)).digest('hex');
function query(scene,source='after',rings=1,frame=true,mode='static',model='procedural') {
  return new URLSearchParams({shipsart:'1',scene,source,rings:String(rings),frame:frame?'1':'0',
    fixture:scene==='fifty'?'large':'partial',motion:mode==='normal'?'normal':'still',model}).toString();
}
async function ready(page) {
  await page.waitForFunction(()=>window.__oceanPreview?.ready||window.__oceanPreview?.error);
  assert.equal(await page.evaluate(()=>window.__oceanPreview.error),undefined);
  await fullyReady(page); await page.mouse.move(1,1);
  const state=await page.evaluate(()=>window.__fogFixture.snapshot().state);
  assert(state.tiles.filter(t=>t.visibility==='hidden').every(t=>t.terrain==='fog'&&t.number==null));
  assert(state.players.filter(p=>p.pid!==state.you_pid).every(p=>!('res'in p)&&!('dev_cards'in p)));
}
async function settings(page) {
  const value=await sceneSettings(page); value.publicStateHash=hash(value.publicState);delete value.publicState;return value;
}
async function useCamera(page,camera) {
  await page.evaluate(value=>{
    const {camera, invalidate}=window.__scene.getState();
    camera.position.fromArray(value.position);camera.quaternion.fromArray(value.quaternion);
    camera.near=value.near;camera.far=value.far;camera.fov=value.fov;
    camera.updateProjectionMatrix();camera.updateMatrixWorld();invalidate();
  },camera);
  await page.waitForTimeout(100);
}
async function inventory(page) {
  return page.evaluate(()=>{
    const {scene,gl}=window.__scene.getState(),materials=new Set(),geometries=new Set();
    const value={meshes:0,instancedMeshes:0,instances:0,decorativeGroups:[]};
    scene.traverse(object=>{
      if(object.userData.decorativeOceanHexes||object.userData.decorativeOceanFrame)
        value.decorativeGroups.push({...object.userData});
      if(!object.isMesh)return;
      value.meshes++;geometries.add(object.geometry.uuid);
      for(const material of Array.isArray(object.material)?object.material:[object.material])materials.add(material.uuid);
      if(object.isInstancedMesh){value.instancedMeshes++;value.instances+=object.count;}
    });
    return {...value,materials:materials.size,sceneGeometries:geometries.size,programs:gl.info.programs.length,
      gpuGeometries:gl.info.memory.geometries,textures:gl.info.memory.textures,
      rings:document.querySelector('[data-ocean-rings]')?.getAttribute('data-ocean-rings')??null,
      cells:document.querySelector('[data-ocean-cells]')?.getAttribute('data-ocean-cells')??null,
      frame:document.querySelector('[data-ocean-frame]')?.getAttribute('data-ocean-frame')??null};
  });
}
async function footprint(page) {
  return page.evaluate(()=>{
    const {scene,camera}=window.__scene.getState();camera.updateMatrixWorld();
    const points=[];scene.traverse(object=>{
      if(!object.isMesh||(!object.userData.decorativeOceanFrame&&!object.userData.oceanFrame))return;
      const position=object.geometry.getAttribute('position');
      for(let index=0;index<position.count;index++){
        const point=object.position.clone().fromBufferAttribute(position,index).applyMatrix4(object.matrixWorld).project(camera);points.push(point.toArray());
      }
    });
    return{framePoints:points.length,allInside:points.every(p=>Math.abs(p[0])<=1.001&&Math.abs(p[1])<=1.001&&p[2]>-1&&p[2]<1)};
  });
}
async function frameCorner(page) {
  return page.evaluate(()=>{
    const {scene,camera,gl}=window.__scene.getState(),rect=gl.domElement.getBoundingClientRect(),points=[];
    scene.traverse(object=>{
      if(!object.userData.decorativeOceanFrame||!object.isMesh)return;
      const position=object.geometry.getAttribute('position');
      for(let index=0;index<position.count;index++){
        const point=object.position.clone().fromBufferAttribute(position,index).applyMatrix4(object.matrixWorld).project(camera);
        if(Math.abs(point.x)<1&&Math.abs(point.y)<1)points.push({x:rect.x+(point.x+1)*rect.width/2,y:rect.y+(1-point.y)*rect.height/2});
      }
    });
    // Select a real visible frame vertex, not a bounding-box corner that may
    // combine unrelated extrema and lie outside the hex-shaped board.
    return points.filter(point=>point.y>rect.y+rect.height*.2&&point.y<rect.y+rect.height*.8).sort((a,b)=>b.x-a.x)[0]||points[0];
  });
}
async function boats(page) {
  return page.evaluate(()=>{
    const {scene,gl,camera}=window.__scene.getState(),roots=[],hooks=[],seen=new Set();
    scene.traverse(object=>{if(object.userData.decorativeBoat)roots.push(object);});
    roots.forEach((root,index)=>root.traverse(mesh=>{if(!mesh.isMesh)return;const original=mesh.onBeforeRender;
      hooks.push([mesh,original]);mesh.onBeforeRender=function(...args){seen.add(index);return original.apply(this,args);};}));
    try{gl.render(scene,camera);}finally{for(const[mesh,original]of hooks)mesh.onBeforeRender=original;}
    return{poses:roots.map(root=>({position:root.position.toArray(),quaternion:root.quaternion.toArray(),scale:root.scale.toArray()})),
      actualMainPassVisibleBoats:seen.size,totalBoats:roots.length};
  });
}
async function normalizeBoats(page,poses) {
  await page.evaluate(values=>{
    const {scene,gl}=window.__scene.getState(),roots=[];scene.traverse(object=>{if(object.userData.decorativeBoat)roots.push(object);});
    if(roots.length!==values.length)throw Error('Decorative boat count changed between paired sources');
    const read=root=>({position:root.position.toArray(),quaternion:root.quaternion.toArray(),scale:root.scale.toArray()});
    const restore=roots.map(read),original=gl.render;
    const apply=(root,value)=>{root.position.fromArray(value.position);root.quaternion.fromArray(value.quaternion);root.scale.fromArray(value.scale);};
    gl.render=function(...args){roots.forEach((root,index)=>{
      // Preserve the latest actual timer pose if a native ambient tick happened.
      if(root.position.toArray().some((value,axis)=>value!==values[index].position[axis]))restore[index]=read(root);
      apply(root,values[index]);
    });return original.apply(this,args);};
    window.__oceanGpuBoatProbe={restore:()=>{gl.render=original;roots.forEach((root,index)=>apply(root,restore[index]));}};
  },poses);
}
async function restoreBoats(page) {await page.evaluate(()=>{window.__oceanGpuBoatProbe?.restore();delete window.__oceanGpuBoatProbe;});}
module.exports={query,ready,settings,useCamera,inventory,footprint,frameCorner,boats,normalizeBoats,restoreBoats,observeScene,idleFrames,hash};
