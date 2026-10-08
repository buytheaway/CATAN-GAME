// Real Chrome + FastAPI recovery + isolated PostgreSQL; no fabricated UI messages.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {chromium}=require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18082';
const h=require('./game-actions.cjs');
const origin=process.env.CATAN_E2E_ORIGIN;
const output=process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(),'catan-f2-hardening');
const checks=[];
const check=text=>{checks.push(text);console.log('PASS '+text);};

async function notice(c){
  await c.page.getByRole('heading',{name:'This match uses an older ruleset'}).waitFor();
  assert.equal(await c.page.locator('.game-shell, canvas').count(),0);
  for(const name of ['Roll','End Turn','Start Match','Rematch'])assert.equal(await c.page.getByRole('button',{name,exact:true}).count(),0);
  assert.equal(c.match,null,'legacy must never receive a playable personalized snapshot');
  assert.equal(c.room.ruleset_compatibility.status,'compatibility_required');
}
async function run(){
  await fs.mkdir(output,{recursive:true});
  const fixtures=JSON.parse(await fs.readFile(process.env.CATAN_F2_FIXTURES,'utf8'));
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const clients=[];
  try {
    const a=await h.newClient(browser,'Fresh Alice');clients.push(a);
    await a.page.evaluate(entries=>localStorage.setItem('catan_recent_games',JSON.stringify({version:1,entries})),
      fixtures.guests.map(x=>({...x,server_url:origin.replace(/^http/,'ws')+'/ws'})));
    await a.page.reload({waitUntil:'networkidle'});
    for(const [i,entry] of fixtures.guests.entries()){
      const card=a.page.locator('.recent-game').filter({hasText:entry.room_code});
      await card.getByRole('button',{name:'View saved match',exact:true}).click();
      await notice(a);
      await a.page.screenshot({path:path.join(output,`legacy-v${i+1}.png`)});
      await a.page.reload({waitUntil:'networkidle'});await notice(a);
      check(`Guest v${i+1}: Home discovery → Continue → compatibility notice → refresh; no game controls or match_state`);
      // A malicious raw command still reaches the authoritative backend gate.
      const error=await a.page.evaluate(()=>new Promise((resolve,reject)=>{
        const ws=window.__sockets.at(-1);const timeout=setTimeout(()=>reject(Error('gate timeout')),10000);
        const listener=e=>{const m=JSON.parse(e.data);if(m.type==='error'){
          clearTimeout(timeout);ws.removeEventListener('message',listener);resolve(m.code);}};
        ws.addEventListener('message',listener);
        ws.send(JSON.stringify({type:'cmd',match_id:1,seq:1,cmd_id:'browser-legacy-probe',cmd:{type:'roll'}}));
      }));
      assert.equal(error,'compatibility_required');
      await a.page.getByRole('button',{name:'Back to Home',exact:true}).click();
      await a.page.getByRole('button',{name:'Host',exact:true}).waitFor();
      assert.equal(await a.page.evaluate(()=>JSON.parse(localStorage.getItem('catan_recent_games')).entries.length),2);
    }
    check('Legacy gameplay rejected on the real socket; Home preserves both guest bindings');
    await a.page.getByLabel('Name',{exact:true}).fill('New Alice');
    await a.page.getByLabel('Max players').fill('2');a.room=null;
    await a.page.getByRole('button',{name:'Host',exact:true}).click();await h.wait(()=>a.room,'new lobby');
    const b=await h.newClient(browser,'New Bob');clients.push(b);
    await b.page.getByLabel('Room code').fill(a.room.room_code);
    await b.page.getByRole('button',{name:'Join',exact:true}).click();
    await h.wait(()=>b.room&&a.room.players.filter(p=>p.connected).length===2,'new pair');
    await a.page.getByRole('button',{name:'Start Match',exact:true}).click();
    await h.wait(()=>a.match&&b.match,'current S1 start');await a.page.locator('.game-shell').waitFor();
    assert.equal(a.room.ruleset_compatibility.status,'compatible');h.privacy([a,b]);
    await a.page.getByRole('button',{name:'2D',exact:true}).click();
    await a.page.locator('svg[height="520"]').waitFor();
    await a.page.screenshot({path:path.join(output,'new-current-match.png')});
    check('Home → new room → two participants → native S1 match with ordinary controls and private projections');

    const account=await h.newClient(browser,'Before login');clients.push(account);
    await account.page.locator('.auth-launch').click();
    const dialog=account.page.getByRole('dialog');
    await dialog.getByLabel('Username',{exact:true}).fill(fixtures.account.username);
    await dialog.getByLabel('Password',{exact:true}).fill(fixtures.account.password);
    await dialog.getByRole('button',{name:'Login',exact:true}).click();await dialog.waitFor({state:'hidden'});
    await account.page.locator('.account-games .recent-game').filter({hasText:fixtures.account.room_code})
      .getByRole('button',{name:'View saved match',exact:true}).click();
    await notice(account);
    await account.page.screenshot({path:path.join(output,'legacy-account.png')});
    await account.page.reload({waitUntil:'networkidle'});await notice(account);
    await account.page.getByRole('button',{name:'Back to Home',exact:true}).click();
    await account.page.locator('.account-games .recent-game').filter({hasText:fixtures.account.room_code}).waitFor();
    check('Account Login → Active Games → restricted Continue → refresh → Home; account seat retained');
    for(const c of clients)assert.deepEqual(c.jsErrors,[]);
    await fs.writeFile(path.join(output,'browser-report.json'),JSON.stringify({checks,jsErrors:[],origin},null,2));
  } finally {await browser.close();}
}
run().catch(e=>{console.error(e.message);process.exitCode=1;});
