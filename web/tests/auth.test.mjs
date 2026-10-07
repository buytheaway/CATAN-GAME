import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

async function load(path) {
  const result = await build({entryPoints:[fileURLToPath(new URL(path, import.meta.url))], bundle:true, write:false, format:"esm", define:{"import.meta.env":"{}"}});
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
}
const api = await load("../src/auth/api.ts");
const {WSClient} = await load("../src/wsClient.ts");
class Socket {
  static OPEN=1; static latest; readyState=0; sent=[];
  constructor(){Socket.latest=this;}
  open(){this.readyState=1;this.onopen();}
  receive(data){this.onmessage({data:JSON.stringify(data)});}
  send(raw){this.sent.push(JSON.parse(raw));}
  close(code=1000){this.readyState=3;this.onclose?.({code});}
}
const store=()=>{const data=new Map();return {get length(){return data.size;},key:i=>[...data.keys()][i]??null,
  getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
beforeEach(()=>{
  globalThis.localStorage=store();globalThis.sessionStorage=store();globalThis.WebSocket=Socket;
  globalThis.window={setTimeout,clearTimeout,location:{protocol:"http:",host:"test"}};
});
const identity=(pid=1,match_id=2,last_seq_applied=7)=>({type:"seat_identity",ownership:"account",room_code:"ABCDEF",pid,match_id,last_seq_applied});
const room={type:"room_state",room_code:"ABCDEF",map_revision:0,host_pid:1,max_players:2,status:"in_match",
  players:[{pid:0,name:"Guest",connected:true},{pid:1,name:"Server name",connected:true}]};
function resumed(){const client=new WSClient();client.continueAccount("ABCDEF","Cached","ws://test/ws");const socket=Socket.latest;socket.open();socket.receive(room);socket.receive(identity());return {client,socket};}

test("account Continue sends only room identity; cookie ownership is not stored as a JS token or pid",()=>{
  const {client,socket}=resumed();
  assert.deepEqual(socket.sent.find(m=>m.type==="account_continue"),{type:"account_continue",room_code:"ABCDEF"});
  assert.equal(client.youPid,1);assert.equal(client.matchId,2);assert.equal(client.seq,7);
  assert.equal(localStorage.length,0);
  const current=JSON.parse(sessionStorage.getItem("catan_current_game"));
  assert.deepEqual(current,{ownership:"account",room_code:"ABCDEF",server_url:"ws://test/ws"});
  assert.equal(client.guestBinding(),null);
});
test("account refresh restores from non-secret pointer and uses server pid/name/sequence",()=>{
  resumed();const client=new WSClient();client.restoreCurrentGame("ws://test/ws");const socket=Socket.latest;
  socket.open();socket.receive(room);socket.receive(identity(0,3,0));
  assert.equal(client.youPid,0);assert.equal(client.matchId,3);assert.equal(client.seq,0);
  assert(!socket.sent.some(m=>m.type==="join_room"||m.type==="reconnect"));
});
test("new match identity resets old pending commands; same-match reconnect consumes confirmed sequence",()=>{
  const {client,socket}=resumed();client.sendCmd({type:"roll"});
  socket.receive(identity(0,3,0));assert.equal(client.seq,0);
  const before=socket.sent.length;socket.receive(identity(0,3,4));
  assert.equal(client.seq,4);assert.equal(socket.sent.length,before);
});
test("claim switches existing socket identity and removes only its guest proof",()=>{
  const client=new WSClient();client.connect("ws://test/ws","Cached");client.host(2);const socket=Socket.latest;socket.open();socket.receive(room);
  socket.receive({...identity(),type:"reconnect_token",reconnect_token:"guest-proof"});
  const data=JSON.parse(localStorage.getItem("catan_recent_games"));
  data.entries.push({room_code:"SECOND",reconnect_token:"unrelated",last_known_name:"Other",last_seen_at:1});
  localStorage.setItem("catan_recent_games",JSON.stringify(data));
  socket.receive(identity());
  assert.equal(client.guestBinding(),null);assert.deepEqual(JSON.parse(localStorage.getItem("catan_recent_games")).entries.map(e=>e.room_code),["SECOND"]);
  assert.equal(JSON.parse(sessionStorage.getItem("catan_current_game")).ownership,"account");
});
for(const code of ["session_expired","seat_taken_over","seat_not_owned","unauthenticated"]){
  test(`${code} ends auto retry without guest Join fallback`,()=>{
    const {client,socket}=resumed();socket.receive({type:"error",code,message:"Stopped"});socket.close(4401);
    assert.equal(client.reconnectTimer,null);assert.equal(sessionStorage.getItem("catan_current_game"),null);
    assert(!socket.sent.some(m=>m.type==="join_room"));
  });
}
test("temporary account persistence failure retains current pointer and reconnect intent",()=>{
  const {client,socket}=resumed();socket.receive({type:"error",code:"persistence_unavailable",message:"Unavailable",detail:{retryable:true}});
  socket.close(1013);assert(client.reconnectTimer);assert(sessionStorage.getItem("catan_current_game"));
  client.leaveRoom();
});
test("manual Host cancels unfinished account reconnect and ignores old identity frames",()=>{
  const client=new WSClient();client.continueAccount("ABCDEF","Cached","ws://test/ws");const old=Socket.latest;old.open();
  client.host(2);assert.equal(old.onmessage,null);const fresh=Socket.latest;fresh.open();
  assert(fresh.sent.some(m=>m.type==="create_room"));assert(!fresh.sent.some(m=>m.type==="account_continue"));
});
test("account API uses same-origin cookie requests and handles safe errors without exposing raw exceptions",async()=>{
  let options;
  globalThis.fetch=async(path,opts)=>{options=opts;return {ok:true,json:async()=>({authenticated:true,user:{username:"alice",display_name:"Дони"}})};};
  await api.authRequest("/api/auth/login",{username:"alice",password:"correct password"});
  assert.equal(options.credentials,"same-origin");assert.equal(options.cache,"no-store");assert(!("Authorization" in options.headers));
  assert.equal(localStorage.length,0);
  globalThis.fetch=async()=>({ok:false,json:async()=>({error:"SQL and secret password"})});
  await assert.rejects(api.getMe(),e=>e.code==="persistence_unavailable"&&!e.message.includes("SQL"));
});
test("malformed account metadata and network failures produce temporary errors",async()=>{
  globalThis.fetch=async()=>({ok:true,json:async()=>({games:[null]})});await assert.rejects(api.getActiveGames(),/persistence_unavailable/);
  globalThis.fetch=async()=>({ok:true,json:async()=>({authenticated:true})});await assert.rejects(api.getMe(),/persistence_unavailable/);
  globalThis.fetch=async()=>{throw Error("network secret");};await assert.rejects(api.getMe(),/persistence_unavailable/);
});
