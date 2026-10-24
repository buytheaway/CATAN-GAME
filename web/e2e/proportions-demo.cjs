// Real public-snapshot Board3D comparison, no trusted map or backend access.
const path=require('node:path'),os=require('node:os');
const {startReadability}=require('./readability-demo.cjs');
const reference='3d82af6c8fc4449bd80b28f8c4bf20bde689e14e';
const scenes=['base','new-shores-4','four-islands-4','fog-before','fog-after','seven','fifty'];
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const output=()=>process.env.CATAN_PROPORTIONS_OUTPUT||path.join(os.tmpdir(),'catan-proportions-5e2');
function comparisonCaptures(report){
 const pairs=new Map();for(const capture of report?.captures||[]){const key=capture.scene+'|'+capture.detail;
  if(!pairs.has(key))pairs.set(key,[]);pairs.get(key).push(capture);}
 return [...pairs.values()].flatMap(pair=>pair.sort((a,b)=>Number(a.source==='after')-Number(b.source==='after')));
}
function gallery(report){return `<!doctype html><meta charset="utf-8"><title>CATAN5E.2 proportions</title><style>body{background:#102332;color:#e9f4fa;font:16px/1.5 system-ui;margin:24px}a{color:#a0e8db}nav{display:flex;gap:16px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}img{width:100%}article{background:#193445;padding:10px}</style><h1>5E.2 · actual tabletop proportions</h1><p>PUBLIC synthetic snapshots, real Board3D. OLD is committed5E.1; NEW is an opt-in proposal, not artistic approval. Production defaults and ships remain unchanged. No hidden Fog recipes. Display occupancy is not a legality-certified match.</p><nav>${scenes.map(scene=>`<a href="/preview?shipsart=1&scene=${scene}&source=after&detail=pilot&rings=1&frame=1&motion=still&fixture=${scene==='fifty'?'large':'partial'}">${scene}</a>`).join('')}</nav><p><a href="/report.json">Actual capture evidence</a></p><div class="grid">${comparisonCaptures(report).map(c=>`<article><a href="/captures/${escape(c.file)}"><img loading="lazy" src="/captures/${escape(c.file)}"></a><p>${escape(c.scene)} · ${escape(c.source)} · ${escape(c.detail)}</p><a href="/preview?${escape(c.query)}">Interactive public scene</a></article>`).join('')}</div>`;}
async function startProportions(port=0){
 const controllerSuffix=`\n(async()=>{while(!window.__readabilityPreview?.ready)await new Promise(r=>setTimeout(r,20));
 const bar=document.querySelector('[data-ocean-preview-toolbar]');bar.querySelector('strong').textContent='5E.2 · opt-in proportions proposal / PUBLIC';
 for(const label of ['Ocean rings','Ocean frame']){const control=bar.querySelector('select[aria-label="'+label+'"]');control.disabled=true;control.title='Fixed one-ring/frame-on for matched proportions';}
 const source=bar.querySelector('select[aria-label="Ocean source"]');source.options[0].textContent='OLD · committed5E.1';source.options[1].textContent='NEW · current + chosen detail';
 const select=document.createElement('select');select.setAttribute('aria-label','Terrain detail proposal');
 for(const[key,text]of [['current','Current proportions'],['pilot','Pilot · sheep + wheat']]){const option=document.createElement('option');option.value=key;option.textContent=text;select.append(option);}
 select.value=new URLSearchParams(location.search).get('detail')||'current';select.onchange=()=>{const url=new URL(location.href);url.searchParams.set('detail',select.value);if(url.searchParams.get('source')==='before'){url.searchParams.set('source','after');location.href=url;}else{history.replaceState(null,'',url);window.dispatchEvent(new CustomEvent('catan-proportions-preview',{detail:select.value}));}};bar.append(select);
 window.__proportionsPreview={ready:true,detail:select.value};
 })().catch(error=>{window.__proportionsPreview={error:error.message};console.error(error);});`;
 return startReadability(port,{reference,output:output(),gallery,controllerSuffix,wrapper:'proportions-wrapper.tsx'});
}
module.exports={startProportions,reference,scenes,comparisonCaptures};
if(require.main===module)startProportions(Number(process.env.CATAN_PROPORTIONS_PORT||18788)).then(d=>console.log('PUBLIC proportions gallery: '+d.origin+'/')).catch(e=>{console.error(e);process.exitCode=1;});
