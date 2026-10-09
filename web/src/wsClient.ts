import type { GameState } from "./components/BoardView.types";
import { clearCurrentGame, currentGame, readRecentGames, removeRecentGame, saveRecentGame, setCurrentGame } from "./recentGames";
import { accountCurrent, setAccountCurrent } from "./auth/api";
import type { RecentGame } from "./recentGames";
import { needsCompatibility } from "./matchCompatibility";
import type { RulesetCompatibility } from "./matchCompatibility";

export type RoomSettings = {
  dice_mode: "random" | "balanced"; starting_player: "random" | "host";
  turn_timer: 0 | 30 | 60 | 90 | 120; bank_visibility: "visible" | "hidden"; target_vp: number; discard_threshold?: number;
};
export type GameplayEvent = {
  id: number; tick: number; at_ms: number; type: string; actor_pid: number;
  player_pid?: number; victim_pid?: number; quantity?: number; resource?: string;
  resources?: Record<string, number>; paid?: Record<string, number>; gained?: Record<string, number>;
  dice?: number[]; total?: number; card?: string; tile?: number; from_tile?: number; action?: string;
};
export type ChatMessage = { id: number; name: string; color: string | null; text: string; sent_at_ms: number };
export type TurnTimerState = {
  pid: number; deadline_ms: number; server_time_ms: number; remaining_ms: number;
  stage: "turn" | "grace" | "blocked" | "stopped";
};
type ChatState = { type: "chat_state"; room_code: string; chat_revision: number; chat_history: ChatMessage[] };

export type RoomState = {
  type: "room_state";
  room_code: string;
  map_revision: number;
  config_revision?: number;
  request_id?: string;
  settings?: RoomSettings;
  chat_history?: ChatMessage[];
  chat_revision?: number;
  host_pid: number;
  test_mode?: boolean;
  players: { pid: number; name: string; connected: boolean; color?: string | null }[];
  max_players: number;
  status: "lobby" | "in_match";
  ruleset_compatibility?: RulesetCompatibility;
  map_id?: string;
  map_meta?: { id?: string; name?: string; description?: string };
  map_presets?: { id: string; name: string; description?: string }[];
  map_rules?: {
    target_vp?: number;
    robber_count?: number;
    max_roads?: number;
    max_settlements?: number;
    max_cities?: number;
    enable_seafarers?: boolean;
    max_ships?: number;
    enable_pirate?: boolean;
    enable_gold?: boolean;
    enable_move_ship?: boolean;
  };
};

export type MatchState = {
  type: "match_state";
  room_code: string;
  match_id: number;
  tick: number;
  state: GameState & {
    you_pid: number;
    players: {
      pid: number;
      name: string;
      color?: string | null;
      vp: number;
      special_vp?: number;
      resource_count: number;
      dev_count: number;
      res?: Record<string, number>;
      dev_cards?: { type: string; new: boolean }[];
    }[];
    rolled: boolean;
    dice?: [number, number] | null;
    roll_count?: number;
    last_roll?: number | null;
    discard_required: Record<string, number>;
    pending_gold: Record<string, number>;
    map_id?: string;
    map_meta?: { name?: string; description?: string };
    bank_available: Record<string, boolean>;
    bank?: Record<string, number>;
    room_settings?: RoomSettings;
    turn_timer?: TurnTimerState | null;
    game_events?: GameplayEvent[];
    test_mode?: boolean;
    test_tools?: boolean;
    game_over?: boolean;
    winner_pid?: number | null;
    free_roads?: Record<string, number>;
    dev_played_turn?: Record<string, boolean>;
    trade_offers?: TradeOffer[];
  };
};

export type TradeOffer = {
  offer_id: number; from_pid: number; to_pid: number | null;
  give: Record<string, number>; get: Record<string, number>;
  status: string; created_turn: number; created_tick: number;
};

export type ServerError = {
  type: "error";
  code: string;
  message: string;
  detail?: Record<string, any>;
};

export type ReconnectTokenMsg = {
  type: "reconnect_token";
  room_code: string;
  pid: number;
  reconnect_token: string;
  last_seq_applied: number;
  match_id: number;
};

export type CmdAck = {
  type: "cmd_ack";
  cmd_id: string;
  seq: number;
  last_seq_applied: number;
  applied: boolean;
  duplicate: boolean;
};

type SeatIdentity = { type: "seat_identity"; ownership: "account"; room_code: string; pid: number; match_id: number; last_seq_applied: number };
export type WsEvent = RoomState | MatchState | ServerError | ReconnectTokenMsg | SeatIdentity | CmdAck | ChatState
  | { type: "hello"; version: number; test_tools_available?: boolean; connection_nonce?: string };

type MapSelection = { mapId: string; payload: Record<string, any> };

export function defaultWebSocketUrl(): string {
  return import.meta.env.PROD
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`
    : import.meta.env.VITE_WS_URL || (window.location?.host
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`
      : "ws://127.0.0.1:8000/ws");
}

function genId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "cmd-" + Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export class WSClient {
  private ws: WebSocket | null = null;
  private url = "";
  private name = "";
  private roomCode: string | null = null;
  private reconnectToken: string | null = null;
  private pendingReconnect: RecentGame | null = null;
  private accountSeat = false;
  public connectionNonce: string | undefined;
  private pendingMatchOperation: { roomCode: string; type: "start_match" | "rematch"; request_id: string; expected_match_id: number } | null = null;
  private reconnectTimer: number | null = null;
  private reconnectDelay = 1000;
  private pendingAction: { type: "host"; maxPlayers: number } | { type: "join"; roomCode: string } | null = null;

  public matchId = 0;
  public seq = 0;
  public lastSeqApplied = 0;
  public youPid: number | null = null;
  public roomState: RoomState | null = null;
  public matchState: MatchState | null = null;
  public testToolsAvailable = false;
  onCapabilities?: () => void;
  enableTestMode() {
    if (this.testToolsAvailable && this.isOpen() && this.roomState?.status === "lobby" && this.youPid === this.roomState.host_pid)
      this.send({ type: "enable_test_mode" });
  }

  private pendingCmds = new Map<string, { seq: number; payload: any }>();
  private matchKey: string | null = null;
  private mapInFlight: { revision: number } | null = null;
  private queuedMap: MapSelection | null = null;
  public pendingMapId: string | null = null;
  private pendingConfig = new Map<string, { settings?: Partial<RoomSettings>; color?: string }>();
  onConfigPending?: () => void;

  get pendingSettings(): Partial<RoomSettings> {
    return Object.assign({}, ...Array.from(this.pendingConfig.values(), p => p.settings ?? {}));
  }
  get pendingColor(): string | undefined {
    return Array.from(this.pendingConfig.values()).filter(p => p.color !== undefined).pop()?.color;
  }
  get configPending(): boolean { return this.pendingConfig.size > 0; }

  private resetConfig() { this.pendingConfig.clear(); this.onConfigPending?.(); }
  private finishConfig(requestId: unknown, confirmed = false) {
    if (typeof requestId !== "string" || !this.pendingConfig.has(requestId)) return;
    if (confirmed) {
      // On one socket a successful later request confirms the server has already
      // processed every earlier request, even if their response frames are delayed.
      for (const id of this.pendingConfig.keys()) {
        this.pendingConfig.delete(id);
        if (id === requestId) break;
      }
    } else this.pendingConfig.delete(requestId);
    this.onConfigPending?.();
  }

  setSettings(settings: Partial<RoomSettings>) {
    if (!this.isOpen() || this.roomState?.status !== "lobby" || this.youPid !== this.roomState.host_pid) return;
    const request_id = genId();
    this.pendingConfig.set(request_id, { settings });
    this.onConfigPending?.();
    this.send({ type: "set_settings", settings, request_id });
  }
  setColor(color: string) {
    if (!this.isOpen() || this.roomState?.status !== "lobby" || this.youPid === null) return;
    const request_id = genId();
    this.pendingConfig.set(request_id, { color });
    this.onConfigPending?.();
    this.send({ type: "set_color", color, request_id });
  }
  sendChat(text: string) {
    if (!this.isOpen() || !this.roomState || this.roomState.room_code !== this.roomCode) return false;
    this.send({ type: "chat", text });
    return true;
  }

  onStatus?: (s: string) => void;
  onRoomState?: (s: RoomState) => void;
  onMapPending?: (mapId: string | null) => void;
  onMatchState?: (s: MatchState) => void;
  onError?: (e: ServerError) => void;
  onLog?: (msg: string) => void;
  // Local notification only; null means reconnect consumed the intent, outcome unknown.
  onCommandSettled?: (cmdId: string, applied: boolean | null) => void;

  isOpen(url?: string): boolean {
    return !!this.ws && this.ws.readyState === WebSocket.OPEN && (!url || this.url === url);
  }

  setName(name: string) {
    this.name = name;
  }

  connect(url: string, name: string) {
    const nextUrl = url || defaultWebSocketUrl();
    if (this.url && this.url !== nextUrl) {
      this.pendingMatchOperation = null;
      this.pendingCmds.clear();
      this.roomState = this.matchState = null;
      this.matchKey = null;
      this.youPid = null;
      this.matchId = this.seq = this.lastSeqApplied = 0;
    }
    // A manual Host/Join can replace a still-connecting refresh attempt.
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.ws) {
      this.ws.onopen = this.ws.onclose = this.ws.onerror = this.ws.onmessage = null;
      this.ws.close();
    }
    this.url = nextUrl;
    this.name = name;
    this.openSocket();
  }

  host(maxPlayers: number) {
    const interruptedReconnect = this.pendingReconnect !== null || this.accountSeat;
    if (interruptedReconnect) this.leaveRoom();
    clearCurrentGame();
    this.pendingMatchOperation = null;
    this.resetConfig();
    this.resetMapSelection();
    this.roomState = null;
    this.roomCode = null;
    this.reconnectToken = null;
    this.pendingReconnect = null;
    this.accountSeat = false;
    this.pendingAction = { type: "host", maxPlayers };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.send({ type: "create_room", name: this.name, max_players: maxPlayers, ruleset: { base: true, max_players: maxPlayers } });
      this.pendingAction = null;
    } else if (interruptedReconnect) {
      this.openSocket();
    }
  }

  join(roomCode: string) {
    this.pendingAction = { type: "join", roomCode };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.sendJoinIntent(roomCode);
      this.pendingAction = null;
    }
  }

  private sendJoinIntent(roomCode: string) {
    if (this.pendingMatchOperation?.roomCode !== roomCode) this.pendingMatchOperation = null;
    this.resetConfig();
    this.resetMapSelection();
    if (this.roomState?.room_code !== roomCode) this.roomState = null;
    if (this.roomCode !== roomCode) this.reconnectToken = null;
    this.roomCode = roomCode;
    if (this.accountSeat) {
      this.pendingReconnect = null;
      this.send({ type: "account_continue", room_code: roomCode });
    } else if (this.reconnectToken) {
      this.pendingReconnect = { room_code: roomCode, reconnect_token: this.reconnectToken, last_known_name: this.name, last_seen_at: 0, server_url: this.url };
      this.send({ type: "reconnect", room_code: roomCode, reconnect_token: this.reconnectToken });
    } else {
      this.pendingReconnect = null;
      this.send({ type: "join_room", room_code: roomCode, name: this.name });
    }
  }

  startMatch() {
    if (this.pendingMapId !== null || this.configPending) {
      this.onLog?.("Wait for room configuration confirmation");
      return;
    }
    this.sendMatchOperation("start_match");
  }

  rematch() {
    this.sendMatchOperation("rematch");
  }

  private sendMatchOperation(type: "start_match" | "rematch") {
    if (needsCompatibility(this.roomState)) return;
    if (!this.isOpen() || !this.roomCode || this.pendingMatchOperation) return;
    this.pendingMatchOperation = { roomCode: this.roomCode, type, request_id: genId(), expected_match_id: this.matchId };
    const { roomCode: _room, ...payload } = this.pendingMatchOperation;
    this.send(payload);
  }

  leaveRoom() {
    clearCurrentGame();
    this.pendingMatchOperation = null;
    this.resetConfig();
    this.send({ type: "leave_room" });
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.ws) {
      this.ws.onclose = this.ws.onmessage = this.ws.onerror = this.ws.onopen = null;
      this.ws.close();
      this.ws = null;
    }
    this.resetMapSelection();
    this.pendingCmds.clear();
    this.pendingAction = null;
    this.roomCode = this.reconnectToken = this.matchKey = null;
    this.pendingReconnect = null;
    this.accountSeat = false;
    this.roomState = this.matchState = null;
    this.youPid = null;
    this.matchId = this.seq = this.lastSeqApplied = 0;
    // Saved room tokens remain available for an explicit later Join.
    this.onStatus?.("idle");
  }

  setMap(mapId?: string, mapData?: Record<string, any>) {
    if (!mapId && !mapData) return;
    if (!this.isOpen() || !this.roomState || this.roomState.room_code !== this.roomCode
        || this.roomState.status !== "lobby" || this.youPid !== this.roomState.host_pid) return;
    const payload: any = { type: "set_map" };
    if (mapId) payload.map_id = mapId;
    if (mapData) payload.map_data = mapData;
    const selection = { mapId: mapData ? mapId || String(mapData.name ?? "custom") : mapId!, payload };
    this.pendingMapId = selection.mapId;
    this.onMapPending?.(this.pendingMapId);
    if (this.mapInFlight) this.queuedMap = selection;
    else this.sendMapSelection(selection);
  }

  private sendMapSelection(selection: MapSelection) {
    // Only one request awaits a result; presence broadcasts cannot acknowledge it.
    this.mapInFlight = { revision: this.roomState!.map_revision + 1 };
    this.send(selection.payload);
  }

  private finishMapSelection() {
    const next = this.queuedMap;
    this.mapInFlight = null;
    this.queuedMap = null;
    if (next && this.roomState?.status === "lobby" && this.isOpen()) {
      this.sendMapSelection(next);
    } else {
      this.resetMapSelection();
    }
  }

  private resetMapSelection() {
    this.mapInFlight = null;
    this.queuedMap = null;
    this.pendingMapId = null;
    this.onMapPending?.(null);
  }

  sendCmd(cmd: Record<string, any>) {
    if (needsCompatibility(this.roomState)) return;
    if (!this.matchId) {
      this.onLog?.("No match yet");
      return;
    }
    const nextSeq = this.seq + 1;
    this.seq = nextSeq;
    const cmdId = genId();
    const payload: any = {
      type: "cmd",
      match_id: this.matchId,
      seq: nextSeq,
      cmd_id: cmdId,
      cmd,
    };
    if (this.roomCode) {
      payload.room_code = this.roomCode;
    }
    this.pendingCmds.set(cmdId, { seq: nextSeq, payload });
    this.send(payload);
    return cmdId;
  }

  private openSocket() {
    if (!this.url) return;
    this.onStatus?.("connecting");
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.onStatus?.("connected");
      this.send({ type: "hello", version: 1, name: this.name });
      if (this.pendingAction?.type === "host") {
        this.send({ type: "create_room", name: this.name, max_players: this.pendingAction.maxPlayers, ruleset: { base: true, max_players: this.pendingAction.maxPlayers } });
        this.pendingAction = null;
      } else if (this.pendingAction?.type === "join") {
        this.sendJoinIntent(this.pendingAction.roomCode);
        this.pendingAction = null;
      } else if (this.roomCode && (this.reconnectToken || this.accountSeat)) {
        this.sendJoinIntent(this.roomCode);
      }
    };
    this.ws.onclose = (event) => {
      if (event?.code === 4401 || event?.code === 4409 || event?.code === 4403) {
        this.pendingAction = null; this.accountSeat = false; this.reconnectToken = null;
        clearCurrentGame();
        this.onError?.({ type: "error", code: event.code === 4409 ? "seat_taken_over" : "session_expired", message: event.code === 4409 ? "This seat was opened in another browser" : "Sign in again" });
      }
      this.resetConfig();
      this.resetMapSelection();
      this.onStatus?.("disconnected");
      this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      this.onStatus?.("error");
    };
    this.ws.onmessage = (ev) => this.handleMessage(ev.data);
  }

  private scheduleReconnect() {
    if (!this.pendingAction && !(this.roomCode && (this.reconnectToken || this.accountSeat))) return;
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    }, this.reconnectDelay);
  }

  private handleMessage(raw: string) {
    let data: WsEvent;
    try {
      data = JSON.parse(raw);
    } catch {
      this.onLog?.("Invalid JSON from server");
      return;
    }
    if (data.type === "hello") {
      this.connectionNonce = data.connection_nonce;
      this.testToolsAvailable = data.test_tools_available === true;
      this.onCapabilities?.();
      return;
    }
    if (data.type === "room_state") {
      if (this.roomCode && data.room_code !== this.roomCode) return;
      this.finishConfig(data.request_id, true);
      if (this.roomState?.room_code === data.room_code
          && (data.config_revision ?? 0) < (this.roomState.config_revision ?? 0)) return;
      if (this.roomState?.room_code === data.room_code
          && data.map_revision < this.roomState.map_revision) return;
      if (this.roomState?.room_code === data.room_code && (data.chat_revision ?? 0) < (this.roomState.chat_revision ?? 0)) {
        data.chat_history = this.roomState.chat_history;
        data.chat_revision = this.roomState.chat_revision;
      }
      this.roomState = data;
      if (needsCompatibility(data)) {
        this.matchState = null;
        this.pendingCmds.clear();
        this.pendingMatchOperation = null;
      }
      this.roomCode = data.room_code;
      const you = data.players.find((p) => p.name === this.name);
      if (you) this.youPid = you.pid;
      if (data.status !== "lobby") { this.resetMapSelection(); this.resetConfig(); }
      else if (this.mapInFlight && data.map_revision >= this.mapInFlight.revision) {
        this.finishMapSelection();
      }
      this.onRoomState?.(data);
      return;
    }
    if (data.type === "chat_state") {
      if (!this.roomState || data.room_code !== this.roomCode
          || data.chat_revision < (this.roomState.chat_revision ?? 0)) return;
      this.roomState = { ...this.roomState, chat_history: data.chat_history, chat_revision: data.chat_revision };
      this.onRoomState?.(this.roomState);
      return;
    }
    if (data.type === "reconnect_token" || data.type === "seat_identity") {
      this.pendingReconnect = null;
      this.reconnectDelay = 1000;
      this.setMatch(data.room_code, data.match_id);
      this.roomCode = data.room_code;
      if (data.type === "seat_identity") {
        const guest = this.guestBinding();
        if (guest) removeRecentGame(guest);
        this.accountSeat = true;
        this.reconnectToken = null;
      } else {
        this.accountSeat = false;
        this.reconnectToken = data.reconnect_token;
      }
      this.lastSeqApplied = data.last_seq_applied ?? 0;
      this.seq = Math.max(this.seq, this.lastSeqApplied);
      const serverName = this.roomState?.players.find(p => p.pid === data.pid)?.name || this.name;
      const identityChanged = this.youPid !== data.pid || this.name !== serverName;
      this.youPid = data.pid;
      this.name = serverName;
      this.persistToken();
      if (this.accountSeat) setAccountCurrent(data.room_code, this.url);
      // A stale cached nickname may not identify us in the earlier room_state.
      if (identityChanged && this.roomState) {
        this.roomState = { ...this.roomState };
        this.onRoomState?.(this.roomState);
      }
      const operation = this.pendingMatchOperation;
      if (operation?.roomCode === data.room_code) {
        if (data.match_id > operation.expected_match_id) this.pendingMatchOperation = null;
        else {
          const { roomCode: _room, ...payload } = operation;
          this.send(payload); // Same request ID and epoch after an interrupted durable operation.
        }
      }
      this.replayPending();
      return;
    }
    if (data.type === "cmd_ack") {
      if (!this.pendingCmds.has(data.cmd_id)) return;
      this.pendingCmds.delete(data.cmd_id);
      this.lastSeqApplied = data.last_seq_applied ?? this.lastSeqApplied;
      this.seq = Math.max(this.seq, this.lastSeqApplied);
      this.onCommandSettled?.(data.cmd_id, data.duplicate ? null : data.applied);
      return;
    }
    if (data.type === "match_state") {
      if (needsCompatibility(this.roomState)) return;
      if (this.roomCode && data.room_code !== this.roomCode) return;
      if (data.room_code === this.roomCode && data.match_id < this.matchId) return;
      if (this.matchState?.match_id === data.match_id && data.room_code === this.matchState.room_code
          && data.tick < this.matchState.tick) return;
      this.setMatch(data.room_code, data.match_id);
      this.youPid = data.state.you_pid;
      this.matchState = data;
      this.matchId = data.match_id;
      this.onMatchState?.(data);
      return;
    }
    if (data.type === "error") {
      if (["session_expired", "unauthenticated", "seat_taken_over", "seat_not_owned"].includes(data.code)) {
        this.accountSeat = false; this.pendingAction = null; this.reconnectToken = null;
        this.pendingCmds.clear(); this.pendingMatchOperation = null; clearCurrentGame();
      }
      if (data.detail?.request_id === this.pendingMatchOperation?.request_id && !data.detail?.retryable)
        this.pendingMatchOperation = null;
      this.finishConfig(data.detail?.request_id);
      if (this.mapInFlight && data.detail?.request_type === "set_map") this.finishMapSelection();
      if (this.pendingReconnect && !data.detail?.retryable && (data.code === "forbidden" || data.code === "not_found")) {
        removeRecentGame(this.pendingReconnect);
        this.reconnectToken = null;
        this.pendingReconnect = null;
        clearCurrentGame();
      }
      if (data.code === "out_of_order") {
        const expected = data.detail?.expected_seq;
        if (typeof expected === "number") {
          this.seq = Math.max(this.seq, expected - 1);
          this.replayPending();
        }
      }
      this.onError?.(data);
    }
  }

  private replayPending() {
    const items = Array.from(this.pendingCmds.values()).sort((a, b) => a.seq - b.seq);
    for (const [cmdId, item] of Array.from(this.pendingCmds.entries())) {
      if (item.seq <= this.lastSeqApplied) {
        this.pendingCmds.delete(cmdId);
        this.onCommandSettled?.(cmdId, null);
      }
    }
    for (const item of items) {
      if (item.seq <= this.lastSeqApplied) continue;
      this.send(item.payload);
    }
  }

  private setMatch(roomCode: string, matchId: number) {
    const key = `${this.url}:${roomCode}:${matchId}`;
    if (this.matchKey === key) return;
    this.matchKey = key;
    this.matchId = matchId;
    this.seq = 0;
    this.lastSeqApplied = 0;
    this.pendingCmds.clear();
  }

  private persistToken() {
    if (!this.roomCode || !this.reconnectToken) return;
    const entry = { room_code: this.roomCode, reconnect_token: this.reconnectToken,
      last_known_name: this.name, last_seen_at: Date.now(), server_url: this.url };
    saveRecentGame(entry);
    setCurrentGame(entry);
  }

  loadToken(roomCode: string, name: string, url = this.url || defaultWebSocketUrl()) {
    if (this.pendingReconnect || this.accountSeat) this.leaveRoom();
    this.roomCode = roomCode;
    this.reconnectToken = null;
    this.pendingReconnect = null;
    this.accountSeat = false;
    this.reconnectToken = readRecentGames().find(entry => entry.room_code === roomCode && entry.last_known_name === name
      && (!entry.server_url || entry.server_url === url))?.reconnect_token ?? null;
  }

  continueGame(entry: RecentGame, url = defaultWebSocketUrl()) {
    this.leaveRoom(); // Fence late callbacks before selecting the saved room.
    this.name = entry.last_known_name;
    this.roomCode = entry.room_code;
    this.reconnectToken = entry.reconnect_token;
    this.join(entry.room_code); // Existing Join intent sends reconnect, never a new seat.
    setCurrentGame(entry); // Temporary failures must keep same-tab refresh recovery available.
    this.connect(entry.server_url || url, this.name);
  }

  guestBinding(): RecentGame | null {
    return this.roomCode && this.reconnectToken ? { room_code: this.roomCode, reconnect_token: this.reconnectToken,
      last_known_name: this.name, last_seen_at: Date.now(), server_url: this.url } : null;
  }

  continueAccount(roomCode: string, name: string, url = defaultWebSocketUrl()) {
    this.leaveRoom();
    this.accountSeat = true;
    this.roomCode = roomCode;
    this.name = name;
    this.join(roomCode);
    setAccountCurrent(roomCode, url);
    this.connect(url, name);
  }

  restoreCurrentGame(url = defaultWebSocketUrl()) {
    const account = accountCurrent();
    if (account && account.server_url === url) { this.continueAccount(account.room_code, "Player", url); return; }
    const entry = currentGame();
    if (entry) this.continueGame(entry, url);
  }

  private send(obj: any) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.onLog?.("Socket not connected");
      return;
    }
    this.ws.send(JSON.stringify(obj));
  }
}
