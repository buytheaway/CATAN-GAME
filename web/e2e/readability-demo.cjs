// Loopback-only real renderer comparison. Never imports trusted Fog recipes.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {startOcean} = require('./ocean-demo.cjs');
const reference = 'b1c5a2f0ae0409a55ba991eb478e8693972fd9c6';
const scenes = ['four-islands-4','base','new-shores-4','fog-before','fog-after','seven','fifty'];
const terrains = ['forest','fields','pasture','hills','mountains','desert','gold'];
const output = () => path.resolve(process.env.CATAN_READABILITY_OUTPUT || path.join(os.tmpdir(),'catan-readability-5e1'));
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function gallery(report) {
  return `<!doctype html><meta charset="utf-8"><title>CATAN 5E.1 readability</title><style>body{background:#102332;color:#e9f4fa;font:16px/1.5 system-ui;margin:24px}a{color:#a0e8db}nav{display:flex;gap:16px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}img{width:100%}article{background:#193445;padding:10px}</style><h1>5E.1 · actual Board3D readability</h1><p>Synthetic PUBLIC snapshots, real renderer. Before: ${reference}; after: working tree. Display occupancy is not a legality-certified match. No hidden Fog assignments. Neither gameplay nor assets are changed.</p><nav>${scenes.map(scene=>`<a href="/preview?shipsart=1&scene=${scene}&source=after&rings=1&motion=still&fixture=${scene==='fifty'?'large':'partial'}">${scene}</a>`).join('')}</nav><p>Use Source for committed/current, Terrain for a synthetic robber standing-area study. Existing orbit/zoom/reset and effect preferences remain available.</p><p><a href="/report.json">Capture evidence</a> · ${escape(report?.checkedAt || 'Captures not recorded yet')}</p><div class="grid">${(report?.captures||[]).map(c=>`<article><a href="/captures/${escape(c.file)}"><img loading="lazy" src="/captures/${escape(c.file)}"></a><p>${escape(c.scene)} · ${escape(c.source)} · ${escape(c.detail||'')}</p><a href="/preview?${escape(c.query)}">Interactive scene</a></article>`).join('')}</div>`;
}
async function startReadability(port=0) {
  let controller = await fs.readFile(path.join(__dirname,'ocean-controller.js'),'utf8');
  // Both 5E.1 sources include 5D.2. Keep exactly the same ocean/frame on both.
  if (!controller.includes('if (source === "before") {')) throw Error('Ocean preview adapter changed; verify the matched baseline');
  controller = controller.replace('if (source === "before") {', 'if (false) {');
  controller += `\n(async()=>{while(!window.__oceanPreview?.ready)await new Promise(r=>setTimeout(r,20));
    const params=new URLSearchParams(location.search), terrain=params.get('terrain');
    if(terrain){const frame=window.__fogFixture.snapshot(),state=frame.state;
      const index=state.tiles.findIndex(t=>t.visibility!=='hidden'&&t.terrain===terrain);
      if(index<0)throw Error('No public terrain '+terrain);state.robber_tile=index;state.robbers=[index];
      state.game_events=[];frame.match_id++;window.__fogFixture.publish(frame);}
    const bar=document.querySelector('[data-ocean-preview-toolbar]');
    bar.querySelector('strong').textContent='5E.1 · actual Board3D / PUBLIC readability';
    const select=document.createElement('select');select.setAttribute('aria-label','Readability terrain');
    for(const key of ['',...${JSON.stringify(terrains)}]){const option=document.createElement('option');option.value=key;option.textContent=key||'Original robber';option.disabled=!!key&&!window.__fogFixture.snapshot().state.tiles.some(t=>t.visibility!=='hidden'&&t.terrain===key);select.append(option);}
    select.value=terrain||'';select.onchange=()=>{const url=new URL(location.href);if(select.value)url.searchParams.set('terrain',select.value);else url.searchParams.delete('terrain');location.href=url;};bar.append(select);
    const sceneSelect=document.querySelector('select[aria-label="Ocean scene"]'),reload=sceneSelect.onchange;
    sceneSelect.onchange=event=>{const url=new URL(location.href);url.searchParams.delete('terrain');history.replaceState(null,'',url);reload.call(sceneSelect,event);};
    window.__readabilityPreview={ready:true,terrain:terrain||null};
  })().catch(error=>{window.__readabilityPreview={error:error.message};console.error(error);});`;
  return startOcean(port,{reference,output:output(),controller,gallery});
}
module.exports={startReadability,reference,scenes,terrains};
if(require.main===module) startReadability(Number(process.env.CATAN_READABILITY_PORT||18787))
  .then(d=>console.log('PUBLIC readability gallery: '+d.origin+'/')).catch(error=>{console.error(error);process.exitCode=1;});
