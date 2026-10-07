// Ordinary UI, real Chrome/Nginx/PostgreSQL, isolated project only. No auth/game mocks.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18081';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(),'catan-auth-phase-1');
const h = require('./game-actions.cjs');
const p = require('./persistence-restart.cjs');
const output=process.env.CATAN_E2E_OUTPUT, origin=process.env.CATAN_E2E_ORIGIN;
const secret='correct horse battery staple';
const unique=Date.now().toString(36);
const users={one:'auth_a_'+unique,two:'auth_b_'+unique,claimed:'auth_g_'+unique};
const checks=[];
function check(value){checks.push(value);console.log('PASS '+value);}
async function form(c, username, display_name) {
  await c.page.locator('.auth-launch').click();
  const dialog=c.page.getByRole('dialog');
  if(display_name) await dialog.getByRole('button',{name:'Create account',exact:true}).click();
  await dialog.getByLabel('Username',{exact:true}).fill(username);
  if(display_name) await dialog.getByLabel('Display name',{exact:true}).fill(display_name);
  await dialog.getByLabel('Password',{exact:true}).fill(secret);
  await dialog.getByRole('button',{name:display_name?'Register':'Login',exact:true}).click();
  await dialog.waitFor({state:'hidden'});
  assert(!await c.page.evaluate(()=>document.cookie.includes('catan_session')),'HttpOnly login cookie must not be visible to JS');
  assert((await c.context.cookies()).some(cookie=>cookie.name==='catan_session'&&cookie.httpOnly&&cookie.sameSite==='Lax'));
}
async function http(c,url,data) {
  return c.page.evaluate(async({url,data})=>{
    const start=performance.now();
    const response=await fetch(url,{method:data===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',
      headers:data===undefined?undefined:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
    return {status:response.status,body:await response.json(),ms:performance.now()-start};
  },{url,data});
}
async function continueAccount(c, code) {
  c.match=null;c.room=null;
  const card=c.page.locator('.account-games .recent-game').filter({hasText:code});
  await card.getByRole('button',{name:'Continue',exact:true}).click();
  await h.wait(()=>c.match&&c.room,'account Continue');
  await c.page.locator('.game-shell').waitFor();
}
async function socketProbe(c, code, proof) {
  return c.page.evaluate(({code,proof})=>new Promise((resolve,reject)=>{
    const start=performance.now();const ws=new WebSocket(location.origin.replace(/^http/,'ws')+'/ws');
    const timeout=setTimeout(()=>{ws.close();reject(Error('probe timeout'));},15000);
    ws.onopen=()=>ws.send(JSON.stringify(proof?{type:'reconnect',room_code:code,reconnect_token:proof}:{type:'account_continue',room_code:code}));
    ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.type==='error'||message.type==='match_state'){
      clearTimeout(timeout);ws.close();resolve({type:message.type,code:message.code,pid:message.state?.you_pid,ms:performance.now()-start});}};
  }),{code,proof});
}
async function run() {
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});const clients=[];
  try {
    const a=await h.newClient(browser,'Before account');clients.push(a);
    await form(a,users.one,'Account Alice');
    await a.page.getByLabel('Max players').fill('2');
    await a.page.getByRole('button',{name:'Host',exact:true}).click();await h.wait(()=>a.room,'account Host');
    const code=a.room.room_code;
    const g=await h.newClient(browser,'Guest Bob');clients.push(g);
    await g.page.getByLabel('Room code').fill(code);await g.page.getByRole('button',{name:'Join',exact:true}).click();
    await h.wait(()=>g.room&&a.room.players[1].connected,'mixed guest Join');
    await a.page.getByLabel('Starting player').selectOption('host');await a.page.getByLabel('Bank resource counts').selectOption('hidden');
    await h.wait(()=>g.room.settings.starting_player==='host'&&g.room.settings.bank_visibility==='hidden','confirmed room settings');
    await a.page.getByRole('button',{name:'Start Match',exact:true}).click();await h.wait(()=>a.match&&g.match,'start mixed match');
    await p.naturalSetup([a,g]);await h.action([a,g],a,()=>a.page.getByRole('button',{name:'Roll',exact:true}).click(),'ordinary account Roll');
    await p.resolvePending([a,g]);await h.layout(a);h.privacy([a,g]);
    const original=p.metadata(code);
    check('Register → account Host → guest Join → natural setup → Roll; mixed room and privacy');

    const b=await h.newClient(browser,'Other browser');clients.push(b);
    await form(b,users.one);
    assert.equal(await b.page.evaluate(()=>localStorage.length),0,'new browser has no guest proof');
    const active=await http(b,'/api/games/active');assert.equal(active.status,200);
    assert(active.body.games.some(game=>game.room_code===code&&game.own_name==='Account Alice'));
    assert(!JSON.stringify(active.body).match(/"(?:res|dev_cards|seed|dice_bag|user_id|password_hash|token_hash)"/));
    await b.page.screenshot({path:path.join(output,'account-home.png')});
    const oldCommands=a.sent.length;
    await continueAccount(b,code);assert.equal(b.match.state.you_pid,0);assert.deepEqual(p.metadata(code),original);
    await h.wait(()=>a.errors.some(e=>e.code==='seat_taken_over'),'old account socket takeover');
    await a.page.locator('.account-games').waitFor();
    await new Promise(r=>setTimeout(r,1400));assert.equal(a.sent.length,oldCommands,'old browser must not auto-reclaim or issue another command');
    check('Second Chrome context → Login → Active Games → same seat; old socket fenced without reclaim loop');

    const c=await h.newClient(browser,'Foreign browser');clients.push(c);await form(c,users.two,'Other account');
    assert.deepEqual((await http(c,'/api/games/active')).body,{games:[]});
    assert.equal((await socketProbe(c,code)).code,'seat_not_owned');assert.deepEqual(p.metadata(code),original);
    check('Different account sees no foreign game and cannot Continue its seat');

    const oldCookie=(await b.context.cookies()).find(cookie=>cookie.name==='catan_session').value;
    await b.page.locator('.auth-launch').click();await b.page.getByRole('button',{name:'Logout',exact:true}).click();
    await b.page.locator('.auth-launch').filter({hasText:'Sign In'}).waitFor();
    const replay=await b.context.request.get(origin+'/api/auth/me',{headers:{Cookie:'catan_session='+oldCookie}});
    assert.deepEqual(await replay.json(),{authenticated:false});
    await form(b,users.one);await continueAccount(b,code);assert.deepEqual(p.metadata(code),original);
    check('Logout revokes server session; replayed old cookie fails; Login/Continue restores same match');

    const before=[p.stable(b),p.stable(g)], durable=p.metadata(code);
    p.docker([...p.compose,'kill','-s','SIGKILL','backend']);p.docker([...p.compose,'up','-d','--wait','backend']);
    await p.freshReconnect(b,code);await p.freshReconnect(g,code);
    assert.deepEqual(p.stable(b),before[0]);assert.deepEqual(p.stable(g),before[1]);assert.deepEqual(p.metadata(code),durable);
    assert.equal((await http(b,'/api/auth/me')).body.authenticated,true);
    check('Backend SIGKILL → durable account session/seat and guest proof recover same private state/deck/bag');

    p.docker([...p.compose,'down']);p.docker([...p.compose,'up','-d','--wait']);
    await p.freshReconnect(b,code);await p.freshReconnect(g,code);
    assert.deepEqual(p.metadata(code),durable);assert.equal((await http(b,'/api/auth/me')).body.authenticated,true);
    check('Full Docker down/up without -v retains users/sessions/ownership/game; account and guest refresh');

    const proof=await g.page.evaluate(()=>JSON.parse(localStorage.getItem('catan_recent_games')).entries[0].reconnect_token);
    const guestName=g.match.state.players[1].name, claimBefore=p.metadata(code), socketsBefore=await g.page.evaluate(()=>window.__sockets.length);
    await form(g,users.claimed,'Account Bob');
    assert(await g.page.evaluate(()=>localStorage.getItem('catan_recent_games').includes('reconnect_token')),'Register must not auto-claim');
    await g.page.locator('.auth-launch').click();await g.page.getByRole('button',{name:'Save to account',exact:true}).click();
    await g.page.getByRole('dialog').waitFor({state:'hidden'});
    assert.equal(await g.page.evaluate(()=>JSON.parse(localStorage.getItem('catan_recent_games')).entries.length),0);
    assert.equal(await g.page.evaluate(()=>window.__sockets.length),socketsBefore,'claim keeps the requesting guest socket');
    assert.deepEqual(p.metadata(code),claimBefore);assert.equal(g.match.state.players[1].name,guestName);
    const inspect=await http(c,'/api/reconnect/inspect-many',{credentials:[{room_code:code,reconnect_token:proof}]});
    assert.deepEqual(inspect.body,{results:[{status:'invalid'}]});
    const guestOnly=await h.newClient(browser,'Former proof');clients.push(guestOnly);
    assert.equal((await socketProbe(guestOnly,code,proof)).code,'forbidden');
    await h.action([b,g],b,()=>b.page.getByRole('button',{name:'End Turn',exact:true}).click(),'End after claim');
    await h.action([b,g],g,()=>g.page.getByRole('button',{name:'Roll',exact:true}).click(),'claimed existing socket Roll');await p.resolvePending([b,g]);
    check('Guest Register is explicit → Save to account atomically revokes proof; same socket/pid/name/state remains usable');

    const d=await h.newClient(browser,'Claimed cross-browser');clients.push(d);await form(d,users.claimed);
    const ownedAfterClaim=p.metadata(code);await continueAccount(d,code);
    assert.equal(d.match.state.you_pid,1);assert.deepEqual(p.metadata(code),ownedAfterClaim);
    check('Claimed seat is available in another browser via account; old guest bearer stays unusable');
    await p.freshReconnect(d,code);assert.equal((await http(d,'/api/auth/me')).body.authenticated,true);
    const retained=p.metadata(code);p.docker([...p.compose,'restart','backend']);await p.freshReconnect(d,code);await p.freshReconnect(b,code);
    assert.deepEqual(p.metadata(code),retained);
    check('Claimed durable ownership and account sessions survive another backend restart');

    const guests=await h.room(browser,'base',2,true);clients.push(...guests);
    await p.naturalSetup(guests);const guestCode=guests[0].room.room_code;
    await guests[0].page.evaluate(()=>sessionStorage.removeItem('catan_current_game'));guests[0].match=null;guests[0].room=null;
    await guests[0].page.reload({waitUntil:'networkidle'});
    await guests[0].page.locator('.recent-game').filter({hasText:guestCode}).getByRole('button',{name:'Continue',exact:true}).click();
    await h.wait(()=>guests[0].match&&guests[0].room,'guest Recent Continue');
    await h.action(guests,guests[0],()=>guests[0].page.getByRole('button',{name:'Roll',exact:true}).click(),'guest regression Roll');
    check('Logged-out Host/Join/Recent/Continue/setup/Roll remains working');

    const perf=await h.newClient(browser,'Timing browser');clients.push(perf);
    const times={login:[],me:[],active_games:[],account_continue:[]};
    for(let i=0;i<6;i++){
      times.login.push((await http(perf,'/api/auth/login',{username:users.one,password:secret})).ms);
      times.me.push((await http(perf,'/api/auth/me')).ms);
      times.active_games.push((await http(perf,'/api/games/active')).ms);
    }
    for(let i=0;i<3;i++){const result=await socketProbe(perf,code);assert.equal(result.type,'match_state');times.account_continue.push(result.ms);}
    const median=values=>values.sort((a,b)=>a-b)[Math.floor(values.length/2)];
    const performance=Object.fromEntries(Object.entries(times).map(([name,values])=>[name+'_median_ms',Math.round(median(values)*10)/10]));
    assert(clients.every(client=>client.jsErrors.length===0),'browser JavaScript errors');
    await fs.writeFile(path.join(output,'results.json'),JSON.stringify({date:new Date().toISOString(),chrome:browser.version(),passed:true,checks,performance},null,2));
    console.log(JSON.stringify({passed:true,checks:checks.length,performance}));
  } finally {for(const c of clients)await c.context.close();await browser.close();}
}
run().catch(e=>{console.error(e.message);process.exit(1);});
