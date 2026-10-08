import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
async function load(path) {
  const result = await build({entryPoints:[fileURLToPath(new URL(path,import.meta.url))],bundle:true,write:false,
    format:"cjs",platform:"node",jsx:"automatic",external:["react","react/jsx-runtime"],
    define:{"import.meta.env":"{}"},loader:{".css":"empty"}});
  const module={exports:{}};
  new Script(`(function(require,module,exports){${result.outputFiles[0].text}\n})`).runInThisContext()(require,module,module.exports);
  return module.exports;
}
const {WSClient}=await load("../src/wsClient.ts");
const {default:LegacyMatchPage}=await load("../src/components/LegacyMatchPage.tsx");
const {default:GameCard}=await load("../src/shell/GameCard.tsx");
class Socket {
  static OPEN=1; static latest; sent=[]; readyState=0;
  constructor(){Socket.latest=this;}
  open(){this.readyState=1;this.onopen();}
  send(raw){this.sent.push(JSON.parse(raw));}
  receive(m){this.onmessage?.({data:JSON.stringify(m)});}
  close(){this.readyState=3;this.onclose?.({code:1000});}
}
const store=()=>{const data=new Map();return{getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
beforeEach(()=>{
  globalThis.localStorage=store();globalThis.sessionStorage=store();globalThis.WebSocket=Socket;
  globalThis.window={setTimeout,clearTimeout,location:{protocol:"http:",host:"test"}};
});
const compatibility={status:"compatibility_required",ruleset_id:null,current_ruleset_id:"catan-seafarers-s1"};
const room={type:"room_state",room_code:"ABCDEF",map_revision:0,config_revision:1,host_pid:0,max_players:2,
  status:"in_match",players:[{pid:0,name:"Alice",connected:true}],map_meta:{name:"Gold Haven"},ruleset_compatibility:compatibility};
function continued(account=false){
  const client=new WSClient();
  if(account)client.continueAccount("ABCDEF","Alice","ws://test/ws");
  else client.continueGame({room_code:"ABCDEF",reconnect_token:"proof",last_known_name:"Alice",last_seen_at:1},"ws://test/ws");
  const socket=Socket.latest;socket.open();socket.receive(room);
  socket.receive({type:account?"seat_identity":"reconnect_token",ownership:"account",room_code:"ABCDEF",pid:0,
    reconnect_token:"proof",match_id:1,last_seq_applied:2});
  return {client,socket};
}
for(const account of [false,true])test(`restricted ${account?"account":"guest"} Continue preserves ownership and suppresses play/retry`,()=>{
  const {client,socket}=continued(account);
  const sent=socket.sent.length;
  client.sendCmd({type:"roll"});client.startMatch();client.rematch();
  assert.equal(socket.sent.length,sent);assert.equal(client.seq,2);
  let received=0;client.onMatchState=()=>received++;
  socket.receive({type:"match_state",room_code:"ABCDEF",match_id:1,tick:99,state:{you_pid:0}});
  assert.equal(received,0);assert.equal(client.matchState,null);
  socket.receive({type:"error",code:"compatibility_required",message:"Restricted"});
  assert(sessionStorage.getItem("catan_current_game"));
  assert.equal(client.youPid,0);
  client.leaveRoom();assert.equal(sessionStorage.getItem("catan_current_game"),null);
  if(!account)assert(localStorage.getItem("catan_recent_games").includes("proof"));
});
test("restricted room cancels stale game and pending commands before reconnect replay",()=>{
  const {client,socket}=continued();
  socket.receive({...room,ruleset_compatibility:{...compatibility,status:"compatible"}});
  socket.receive({type:"match_state",room_code:"ABCDEF",match_id:1,tick:0,state:{you_pid:0}});
  client.sendCmd({type:"roll"});assert.equal(client.pendingCmds.size,1);
  socket.receive(room);assert.equal(client.matchState,null);assert.equal(client.pendingCmds.size,0);
  const count=socket.sent.length;
  socket.receive({type:"reconnect_token",room_code:"ABCDEF",reconnect_token:"proof",pid:0,match_id:1,last_seq_applied:2});
  assert.equal(socket.sent.length,count);
});
test("legacy notice explains preserved data and offers Home without gameplay controls",()=>{
  const html=renderToStaticMarkup(React.createElement(LegacyMatchPage,{room,onHome(){}}));
  assert.match(html,/older ruleset/);assert.match(html,/Back to Home/);assert.match(html,/preserved/);
  assert.match(html,/host a new game/);assert.match(html,/Gold Haven/);
  assert.doesNotMatch(html,/Roll|End Turn|Start Match|<canvas|Dev Card/);
});
test("restricted Continue card remains navigable and is not labeled corrupted or unavailable",()=>{
  const html=renderToStaticMarkup(React.createElement(GameCard,{code:"ABCDEF",loading:false,onContinue(){},
    game:{map_name:"Gold Haven",own_name:"Alice",own_color:"red",status:"active",can_continue:true,ruleset_compatibility:compatibility}}));
  assert.match(html,/Compatibility required/);assert.match(html,/View saved match/);
  assert.doesNotMatch(html,/disabled|corrupt|Temporarily unavailable/);
});
test("Home to new room clears the previous compatibility state",()=>{
  const {client}=continued();client.leaveRoom();client.connect("ws://test/ws","Alice");client.host(2);
  const socket=Socket.latest;socket.open();
  socket.receive({...room,room_code:"NEW123",status:"lobby",ruleset_compatibility:undefined});
  socket.receive({type:"reconnect_token",room_code:"NEW123",pid:0,match_id:0,last_seq_applied:0,reconnect_token:"new-proof"});
  client.startMatch();assert(socket.sent.some(m=>m.type==="start_match"));
});
