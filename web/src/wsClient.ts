import type { GameState } from "./components/BoardView.types";

export type RoomState = {
  type: "room_state";
  room_code: string;
  map_revision: number;
  host_pid: number;
  players: { pid: number; name: string; connected: boolean }[];
  max_players: number;
  status: "lobby" | "in_match";
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
      vp: number;
      resource_count: number;
      dev_count: number;
      res?: Record<string, number>;
      dev_cards?: { type: string; new: boolean }[];
    }[];
    rolled: boolean;
    discard_required: Record<string, number>;
    pending_gold: Record<string, number>;
    map_id?: string;
    map_meta?: { name?: string; description?: string };
    bank_available: Record<string, boolean>;
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

export type WsEvent = RoomState | MatchState | ServerError | ReconnectTokenMsg | CmdAck;

type MapSelection = { mapId: string; payload: Record<string, any> };

export function defaultWebSocketUrl(): string {
  return import.meta.env.PROD
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`
    : import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8000/ws";
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
  private pendingReconnectKey: string | null = null;
  private reconnectTimer: number | null = null;
  private reconnectDelay = 1000;
  private pendingAction: { type: "host"; maxPlayers: number } | { type: "join"; roomCode: string } | null = null;

  public matchId = 0;
  public seq = 0;
  public lastSeqApplied = 0;
  public youPid: number | null = null;
  public roomState: RoomState | null = null;
  public matchState: MatchState | null = null;

  private pendingCmds = new Map<string, { seq: number; payload: any }>();
  private matchKey: string | null = null;
  private mapInFlight: { revision: number } | null = null;
  private queuedMap: MapSelection | null = null;
  public pendingMapId: string | null = null;

  onStatus?: (s: string) => void;
  onRoomState?: (s: RoomState) => void;
  onMapPending?: (mapId: string | null) => void;
  onMatchState?: (s: MatchState) => void;
  onError?: (e: ServerError) => void;
  onLog?: (msg: string) => void;
  // Local notification only; null means reconnect consumed the intent, outcome unknown.
  onCommandSettled?: (cmdId: string, applied: boolean | null) => void;

  isOpen(): boolean {
    return !!this.ws && this.ws.readyState === WebSocket.OPEN;
  }

  setName(name: string) {
    this.name = name;
  }

  connect(url: string, name: string) {
    this.url = url || defaultWebSocketUrl();
    this.name = name;
    this.openSocket();
  }

  host(maxPlayers: number) {
    this.resetMapSelection();
    this.roomState = null;
    this.roomCode = null;
    this.reconnectToken = null;
    this.pendingReconnectKey = null;
    this.pendingAction = { type: "host", maxPlayers };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.send({ type: "create_room", name: this.name, max_players: maxPlayers, ruleset: { base: true, max_players: maxPlayers } });
      this.pendingAction = null;
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
    this.resetMapSelection();
    if (this.roomState?.room_code !== roomCode) this.roomState = null;
    if (this.roomCode !== roomCode) this.reconnectToken = null;
    this.roomCode = roomCode;
    if (this.reconnectToken) {
      this.pendingReconnectKey = `catan_reconnect_${roomCode}_${this.name}`;
      this.send({ type: "reconnect", room_code: roomCode, reconnect_token: this.reconnectToken });
    } else {
      this.pendingReconnectKey = null;
      this.send({ type: "join_room", room_code: roomCode, name: this.name });
    }
  }

  startMatch() {
    if (this.pendingMapId !== null) {
      this.onLog?.("Wait for map confirmation");
      return;
    }
    this.send({ type: "start_match" });
  }

  rematch() {
    this.send({ type: "rematch" });
  }

  leaveRoom() {
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
    this.roomCode = this.reconnectToken = this.pendingReconnectKey = this.matchKey = null;
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
      this.reconnectDelay = 1000;
      this.send({ type: "hello", version: 1, name: this.name });
      if (this.pendingAction?.type === "host") {
        this.send({ type: "create_room", name: this.name, max_players: this.pendingAction.maxPlayers, ruleset: { base: true, max_players: this.pendingAction.maxPlayers } });
        this.pendingAction = null;
      } else if (this.pendingAction?.type === "join") {
        this.sendJoinIntent(this.pendingAction.roomCode);
        this.pendingAction = null;
      } else if (this.roomCode && this.reconnectToken) {
        this.sendJoinIntent(this.roomCode);
      }
    };
    this.ws.onclose = () => {
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
    if (data.type === "room_state") {
      if (this.roomCode && data.room_code !== this.roomCode) return;
      if (this.roomState?.room_code === data.room_code
          && data.map_revision < this.roomState.map_revision) return;
      this.roomState = data;
      this.roomCode = data.room_code;
      const you = data.players.find((p) => p.name === this.name);
      if (you) this.youPid = you.pid;
      if (data.status !== "lobby") this.resetMapSelection();
      else if (this.mapInFlight && data.map_revision >= this.mapInFlight.revision) {
        this.finishMapSelection();
      }
      this.onRoomState?.(data);
      return;
    }
    if (data.type === "reconnect_token") {
      this.pendingReconnectKey = null;
      this.setMatch(data.room_code, data.match_id);
      this.roomCode = data.room_code;
      this.reconnectToken = data.reconnect_token;
      this.lastSeqApplied = data.last_seq_applied ?? 0;
      this.seq = Math.max(this.seq, this.lastSeqApplied);
      this.youPid = data.pid;
      this.persistToken();
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
      if (this.mapInFlight && data.detail?.request_type === "set_map") this.finishMapSelection();
      if (this.pendingReconnectKey && (data.code === "forbidden" || data.code === "not_found")) {
        this.reconnectToken = null;
        try {
          localStorage.removeItem(this.pendingReconnectKey);
        } catch {
          // Storage may be unavailable; still report the server rejection.
        }
        this.pendingReconnectKey = null;
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
    const key = `${roomCode}:${matchId}`;
    if (this.matchKey === key) return;
    this.matchKey = key;
    this.matchId = matchId;
    this.seq = 0;
    this.lastSeqApplied = 0;
    this.pendingCmds.clear();
  }

  private persistToken() {
    if (!this.roomCode || !this.reconnectToken) return;
    const key = `catan_reconnect_${this.roomCode}_${this.name}`;
    localStorage.setItem(key, JSON.stringify({ token: this.reconnectToken, pid: this.youPid ?? 0 }));
  }

  loadToken(roomCode: string, name: string) {
    const key = `catan_reconnect_${roomCode}_${name}`;
    this.roomCode = roomCode;
    this.reconnectToken = null;
    this.pendingReconnectKey = null;
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return;
      const data = JSON.parse(raw);
      this.reconnectToken = typeof data.token === "string" && data.token ? data.token : null;
    } catch {
      return;
    }
  }

  private send(obj: any) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.onLog?.("Socket not connected");
      return;
    }
    this.ws.send(JSON.stringify(obj));
  }
}
