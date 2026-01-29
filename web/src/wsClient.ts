export type RoomState = {
  type: "room_state";
  room_code: string;
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
  };
};

export type MatchState = {
  type: "match_state";
  room_code: string;
  match_id: number;
  tick: number;
  seed: number;
  state: Record<string, any>;
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

const DEFAULT_WS_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8000/ws";

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

  onStatus?: (s: string) => void;
  onRoomState?: (s: RoomState) => void;
  onMatchState?: (s: MatchState) => void;
  onError?: (e: ServerError) => void;
  onLog?: (msg: string) => void;

  connect(url: string, name: string) {
    this.url = url || DEFAULT_WS_URL;
    this.name = name;
    this.openSocket();
  }

  host(maxPlayers: number) {
    this.pendingAction = { type: "host", maxPlayers };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.send({ type: "create_room", name: this.name, max_players: maxPlayers, ruleset: { base: true, max_players: maxPlayers } });
      this.pendingAction = null;
    }
  }

  join(roomCode: string) {
    this.pendingAction = { type: "join", roomCode };
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.send({ type: "join_room", room_code: roomCode, name: this.name });
      this.pendingAction = null;
    }
  }

  startMatch() {
    this.send({ type: "start_match" });
  }

  rematch() {
    this.send({ type: "rematch" });
  }

  setMap(mapId: string) {
    this.send({ type: "set_map", map_id: mapId });
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
  }

  private openSocket() {
    if (!this.url) return;
    this.onStatus?.("connecting");
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.onStatus?.("connected");
      this.reconnectDelay = 1000;
      this.send({ type: "hello", version: 1, name: this.name });
      if (this.roomCode && this.reconnectToken) {
        this.send({ type: "reconnect", room_code: this.roomCode, reconnect_token: this.reconnectToken });
      } else if (this.pendingAction?.type === "host") {
        this.send({ type: "create_room", name: this.name, max_players: this.pendingAction.maxPlayers, ruleset: { base: true, max_players: this.pendingAction.maxPlayers } });
        this.pendingAction = null;
      } else if (this.pendingAction?.type === "join") {
        this.send({ type: "join_room", room_code: this.pendingAction.roomCode, name: this.name });
        this.pendingAction = null;
      }
    };
    this.ws.onclose = () => {
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
      this.roomState = data;
      this.roomCode = data.room_code;
      const you = data.players.find((p) => p.name === this.name);
      if (you) this.youPid = you.pid;
      this.onRoomState?.(data);
      return;
    }
    if (data.type === "reconnect_token") {
      this.reconnectToken = data.reconnect_token;
      this.lastSeqApplied = data.last_seq_applied ?? 0;
      this.seq = Math.max(this.seq, this.lastSeqApplied);
      this.youPid = data.pid;
      this.persistToken();
      this.replayPending();
      return;
    }
    if (data.type === "cmd_ack") {
      this.pendingCmds.delete(data.cmd_id);
      this.lastSeqApplied = data.last_seq_applied ?? this.lastSeqApplied;
      this.seq = Math.max(this.seq, this.lastSeqApplied);
      return;
    }
    if (data.type === "match_state") {
      this.matchState = data;
      this.matchId = data.match_id;
      this.onMatchState?.(data);
      return;
    }
    if (data.type === "error") {
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
    for (const item of items) {
      if (item.seq <= this.lastSeqApplied) {
        continue;
      }
      this.send(item.payload);
    }
  }

  private persistToken() {
    if (!this.roomCode || !this.reconnectToken) return;
    const key = `catan_reconnect_${this.roomCode}_${this.name}`;
    localStorage.setItem(key, JSON.stringify({ token: this.reconnectToken, pid: this.youPid ?? 0 }));
  }

  loadToken(roomCode: string, name: string) {
    const key = `catan_reconnect_${roomCode}_${name}`;
    const raw = localStorage.getItem(key);
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      this.reconnectToken = data.token || null;
      this.roomCode = roomCode;
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
