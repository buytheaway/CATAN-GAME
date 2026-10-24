// Loopback-only real Board3D; synthetic PUBLIC snapshots, no DB/private recipe.
const path = require('node:path'), os = require('node:os');
const { startReadability } = require('./readability-demo.cjs');
const reference = 'e01e8fb45e501a55aa6cd3d3b4bf51bb59fe5a21';
const scenes = ['base', 'new-shores-3', 'new-shores-4', 'four-islands-3', 'four-islands-4', 'fog-before', 'fog-after', 'seven', 'fifty'];
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const output = () => process.env.CATAN_WATER_OUTPUT || path.join(os.tmpdir(), 'catan-water-5f1');
function gallery(report) {
  const groups = new Map();
  for (const c of report?.captures || []) {
    const key = [c.scene, c.rings, c.detail].join('|');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const captures = [...groups.values()].flatMap(pair => pair.sort((a, b) => Number(a.source === 'after') - Number(b.source === 'after')));
  return `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CATAN 5F.1 water materials</title>
    <style>body{background:#102332;color:#e9f4fa;font:16px/1.5 system-ui;margin:24px}a{color:#a0e8db}nav{display:flex;gap:16px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}img{width:100%}article{background:#193445;padding:10px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>
    <h1>5F.1 · actual Board3D water comparison</h1><p>PUBLIC synthetic snapshots. OLD: committed ${reference}; NEW: opt-in material proposal, not approved art. Geometry, frame, camera, terrain proportions and procedural ship default are preserved. Display occupancy is not a legality-certified match. No private Fog recipe.</p>
    <nav>${scenes.map(scene => `<a href="/preview?shipsart=1&scene=${scene}&source=after&water=pilot&rings=1&frame=1&motion=still&fixture=${scene === 'fifty' ? 'large' : 'partial'}">${scene}</a>`).join('')}</nav><p>Current / Water Pilot changes materials live without resetting camera. One/two rings and Frame controls remain available.</p>
    <p><a href="/report.json">Raw capture evidence</a></p><div class="grid">${captures.map(c => `<article><a href="/captures/${escape(c.file)}"><img loading="lazy" src="/captures/${escape(c.file)}"></a><p>${escape(c.scene)} · ${escape(c.source)} · rings ${c.rings} · ${escape(c.detail)}</p><a href="/preview?${escape(c.query)}">Same interactive scene</a></article>`).join('')}</div>`;
}
async function startWater(port = 0) {
  const controllerSuffix = `\n(async()=>{
    while(!window.__readabilityPreview?.ready)await new Promise(r=>setTimeout(r,20));
    const bar=document.querySelector('[data-ocean-preview-toolbar]'),params=new URLSearchParams(location.search);
    bar.querySelector('strong').textContent='5F.1 · opt-in water material / PUBLIC';
    bar.querySelector('[aria-label="Readability terrain"]')?.remove();
    const source=bar.querySelector('[aria-label="Ocean source"]');
    source.options[0].textContent='OLD · committed current water';source.options[1].textContent='NEW · current + water option';
    const select=document.createElement('select');select.setAttribute('aria-label','Water appearance');
    for(const[key,text]of [['current','Current water'],['pilot','Water Pilot · provisional']]){const option=document.createElement('option');option.value=key;option.textContent=text;select.append(option);}
    select.value=params.get('source')==='before'?'current':params.get('water')||'current';
    select.onchange=()=>{const url=new URL(location.href);url.searchParams.set('water',select.value);
      if(url.searchParams.get('source')==='before'){url.searchParams.set('source','after');location.href=url;}
      else{history.replaceState(null,'',url);window.dispatchEvent(new CustomEvent('catan-water-preview',{detail:select.value}));}};bar.append(select);
    const rings=bar.querySelector('[aria-label="Ocean rings"]'),border=bar.querySelector('[aria-label="Ocean frame"]');
    const updateOcean=()=>{const url=new URL(location.href);url.searchParams.set('rings',rings.value);url.searchParams.set('frame',border.value);
      history.replaceState(null,'',url);window.dispatchEvent(new CustomEvent('catan-ocean-preview',{detail:{rings:Number(rings.value),frame:border.value==='1'}}));};
    rings.onchange=updateOcean;border.onchange=updateOcean;
    // Display-only public pirate placement; never inferred from unknown Fog.
    const frame=window.__fogFixture.snapshot(),state=frame.state;
    if(state.rules_config?.enable_seafarers&&!(state.pirate_tile>=0)){
      const tile=state.tiles.findIndex(t=>t.visibility!=='hidden'&&t.terrain==='sea');
      if(tile>=0){state.pirate_tile=tile;frame.tick++;window.__fogFixture.publish(frame);}
    }
    window.__waterPreview={ready:true,synthetic:true};
  })().catch(error=>{window.__waterPreview={error:error.message};console.error(error);});`;
  return startReadability(port, { reference, output: output(), gallery, controllerSuffix, wrapper: 'water-wrapper.tsx' });
}
module.exports = { startWater, reference, scenes };
if (require.main === module) startWater(Number(process.env.CATAN_WATER_PORT || 18789))
  .then(demo => console.log('PUBLIC water gallery: ' + demo.origin + '/'))
  .catch(error => { console.error(error); process.exitCode = 1; });
