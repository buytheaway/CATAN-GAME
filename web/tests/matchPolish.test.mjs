import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as jsxRuntime from "react/jsx-runtime";
import { Mesh, BoxGeometry, MeshBasicMaterial, Raycaster, Vector3 } from "three";

const require = createRequire(import.meta.url);
const compiled = await build({ stdin: {
  contents: `export {default as GamePage} from "./components/GamePage";
    export {default as GameLog} from "./game/GameLog";
    export {testModeAccess} from "./game/TestTools";
    export {GameTopBar, PlayerStrip} from "./game/GameHUD";
    export {default as GameIcon} from "./game/GameIcon";
    export {RESOURCE_ICON_PATHS} from "./game/resourceIcons";
    export {portAppearance} from "./board3d/materials";
    export * from "./board3d/environment";`,
  resolveDir: fileURLToPath(new URL("../src/", import.meta.url)), loader: "tsx" },
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  external: ["react", "react/jsx-runtime"], loader: { ".css": "empty" },
  plugins: [{name:"no-webgl", setup(b) { b.onLoad({filter:/board3d[\\/]Board3D\.tsx$/}, () => ({contents:'export default function Board3D(){return null}',loader:"tsx"})); }}],
});
let elements = [];
const traced = { ...jsxRuntime, ...Object.fromEntries(["jsx", "jsxs"].map(key => [key, (type, props, id) => {
  if (typeof type === "string") elements.push({type,...props});
  return jsxRuntime[key](type, props, id);
}])) };
const loaded = {exports:{}};
new Script(`(function(require,module,exports){${compiled.outputFiles[0].text}\n})`).runInThisContext()(
  name => name === "react/jsx-runtime" ? traced : require(name), loaded, loaded.exports);
const {GamePage,GameLog,GameTopBar,PlayerStrip,GameIcon,RESOURCE_ICON_PATHS,portAppearance,testModeAccess,
  decorativeShipsEnabled,oceanClearance,ambientBoatPose,ignoreSceneryRaycast} = loaded.exports;
function render(Component,props) {
  elements=[];
  const html = renderToStaticMarkup(React.createElement(Component,props));
  return {html,elements};
}
function snapshot(extra={}) {
  return {size:58, tiles:[{terrain:"forest",q:0,r:0}],vertices:{},edges:[],occupied_v:{},occupied_e:{},occupied_ships:{},
    robber_tile:0,pirate_tile:null,phase:"main",turn:0,rolled:true,pending_action:null,discard_required:{},pending_gold:{},
    players:[{pid:0,name:"Alice",vp:3,resource_count:5,dev_count:0,res:{wood:1}},{pid:1,name:"Bob",vp:2,resource_count:7,dev_count:2}],
    rules_config:{target_vp:10},map_meta:{name:"Base Standard"},test_mode:false,test_tools:false,
    legal:{pid:0,settlements:[],roads:[],cities:[],ships:[]},...extra};
}
function top(state=snapshot(),extra={}) {
  return render(GameTopBar,{state,pid:0,roomCode:"ROOM",drawer:null,onInfo(){},onLog(){},...extra});
}

test("all five specialized ports map to the existing card/bank resource icon and 2:1; generic is 3:1", () => {
  assert.equal(portAppearance("3:1").label,"3:1"); assert.equal(portAppearance("3:1").resource,undefined);
  for(const resource of ["wood","brick","sheep","wheat","ore"]) {
    const visual=portAppearance(`2:1:${resource}`);
    assert.equal(visual.label,"2:1"); assert.equal(visual.resource,resource);
    const icon=render(GameIcon,{name:visual.resource}).html;
    for(const path of RESOURCE_ICON_PATHS[resource]) assert(icon.includes(`d="${path}"`));
    assert(/^#[0-9a-f]{6}$/i.test(visual.color));
  }
  assert.equal(portAppearance("unknown").label,"?");
  assert.equal(portAppearance("2:1:toString").resource,undefined);
});

test("match has Bank first, public Players second, permanent Chat third and a separately closed Game Log", () => {
  const state=snapshot();
  const view=render(GamePage,{client:{youPid:0,isOpen:()=>true,sendCmd(){},sendChat(){return true;}},
    match:{room_code:"ROOM",match_id:1,tick:1,state},room:{players:[],chat_history:[{id:1,name:"Bob",color:"blue",text:"Still here <b>!",sent_at_ms:1000}]},
    status:"connected",log:["PRIVATE_TRANSPORT_SENTINEL"],error:null});
  const bank=view.html.indexOf('class="bank-summary"'), players=view.html.indexOf('class="sidebar-players"'),chat=view.html.indexOf('class="sidebar-chat"');
  assert(bank<players&&players<chat);
  assert.match(view.html,/aria-label="Room chat"/);assert.match(view.html,/Still here &lt;b&gt;!/);
  assert(view.elements.some(e=>e.type==="input"&&e.id==="room-chat-input"&&!e.disabled));
  assert.doesNotMatch(view.html,/role="tablist"|PRIVATE_TRANSPORT_SENTINEL|Game Log \/ Chat|game-log-content" id=/);
  assert(view.elements.find(e=>e["aria-controls"]==="game-log-content")["aria-expanded"]===false);
});

test("opening the separate log renders only server-personalized events and delegates its own toggle", () => {
  const state=snapshot({game_events:[{id:1,type:"theft",actor_pid:0,victim_pid:1,at_ms:1000}]});
  let toggles=0;
  const props={state,transport:["socket opened"],onToggle:()=>toggles++};
  assert.doesNotMatch(render(GameLog,{...props,open:false}).html,/stole|socket opened|Room chat/);
  const view=render(GameLog,{...props,open:true});
  assert.match(view.html,/Alice stole a resource from Bob/);assert.match(view.html,/socket opened/);
  assert.doesNotMatch(view.html,/Room chat|wood|knight|victory_point/);
  view.elements.find(e=>e.type==="button").onClick();assert.equal(toggles,1);
  state.game_events[0].resource="ore";
  assert.match(render(GameLog,{...props,open:true}).html,/stole 1 ore/);
});

test("Test Mode requires both server snapshot flags, a connection and an unfinished match", () => {
  for(const [flags,status,available,want] of [
    [{},"connected",false,false], [{},"connected",true,false],
    [{test_mode:true},"connected",true,false], [{test_tools:true},"connected",true,false],
    [{test_mode:true,test_tools:true},"connected",true,true],
    [{test_mode:true,test_tools:true},"reconnecting",true,false],
    [{test_mode:true,test_tools:true,game_over:true},"connected",true,false],
  ]) assert.equal(testModeAccess(snapshot(flags),status,available).canUse,want);
  assert.match(testModeAccess(snapshot(),"connected",false).description,/disabled on this server/);
  assert.match(testModeAccess(snapshot(),"connected",true).description,/lobby before starting/);
  assert.match(testModeAccess(snapshot({test_mode:true}),"connected",true).description,/Only the current host/);
});

test("compact header exposes exact identity/connection/map/goal and TEST MODE only in a test room", () => {
  const ordinary=top();
  for(const text of ["CATAN.КОЛОНИЗАТОРЫ","Base Standard","ROOM","10 VP","Online"])assert(ordinary.html.includes(text));
  assert.doesNotMatch(ordinary.html,/TEST MODE|aria-label="Test Tools"/);
  assert.doesNotMatch(top(snapshot({test_mode:true})).html,/aria-label="Test Tools"/);
  let clicked=0;
  const testState=snapshot({test_mode:true,test_tools:true});
  const view=top(testState,{onTest:()=>clicked++,testAvailable:true});
  const trigger=view.elements.find(e=>e["aria-label"]==="Test Tools");assert(!trigger.disabled);trigger.onClick();assert.equal(clicked,1);
  assert.match(view.html,/TEST MODE|Non-production Test Room/);
  assert(top(testState,{onTest(){},testAvailable:false,status:"reconnecting"}).elements.find(e=>e["aria-label"]==="Test Tools").disabled);
});

test("player presence and host badges come from Room; public counts remain independent of hidden hands", () => {
  const state=snapshot();state.players[1].res={SECRET_RESOURCE:22};state.players[1].dev_cards=[{type:"SECRET_CARD"}];
  const html=render(PlayerStrip,{state,pid:0,room:{host_pid:0,players:[{pid:0,connected:true},{pid:1,connected:false}]}}).html;
  assert.match(html,/Connected/);assert.match(html,/Disconnected/);assert.match(html,/host/);assert.match(html,/7 resource cards/);
  assert.doesNotMatch(html,/SECRET_RESOURCE|SECRET_CARD/);
  assert.doesNotMatch(render(PlayerStrip,{state,pid:0,room:null}).html,/Disconnected|Connected|player-role/);
});

test("ambient boats are Base-only: real sea, Seafarers, player ships or a pirate suppress them", () => {
  const state=snapshot();assert.equal(decorativeShipsEnabled(state),true);
  for(const extra of [{rules_config:{enable_seafarers:true}},{tiles:[{terrain:"sea"}]},
    {occupied_ships:{"1,2":0}},{pirate_tile:0},{tiles:[]}])assert.equal(decorativeShipsEnabled(snapshot(extra)),false);
});

test("varied decorative routes stay outside every actual tile, including shifted maps, without mutating bounds", () => {
  const model={bounds:{center:[40,0,-17]},tiles:[{position:[43,0,-17]},{position:[37,0,-13]},{position:[36,0,-21]}]};
  const before=JSON.stringify(model),clearance=oceanClearance(model);
  for(let i=0;i<3;i++)for(let seconds=0;seconds<1800;seconds+=17) {
    const pose=ambientBoatPose(model.bounds.center,clearance,i,seconds);
    for(const tile of model.tiles)assert(Math.hypot(pose.position[0]-tile.position[0],pose.position[2]-tile.position[2])>1.35);
    assert(Number.isFinite(pose.rotation));
  }
  assert.notDeepEqual(ambientBoatPose(model.bounds.center,clearance,0,12),ambientBoatPose(model.bounds.center,clearance,1,12));
  assert.equal(JSON.stringify(model),before);
});

test("scenery raycast exclusion produces no hit even when the ray goes through its geometry", () => {
  const geometry=new BoxGeometry(),material=new MeshBasicMaterial(),mesh=new Mesh(geometry,material);
  const ray=new Raycaster(new Vector3(0,0,3),new Vector3(0,0,-1));mesh.updateMatrixWorld();
  assert(ray.intersectObject(mesh).length>0);mesh.raycast=ignoreSceneryRaycast;
  assert.deepEqual(ray.intersectObject(mesh),[]);geometry.dispose();material.dispose();
});
