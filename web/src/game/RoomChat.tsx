import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../wsClient";
import { ROOM_COLORS } from "../board/colors";

export default function RoomChat({ messages, send, disabled = false }: {
  messages: ChatMessage[]; send: (text: string) => boolean; disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const history = useRef<HTMLOListElement>(null);
  useEffect(() => { if (history.current) history.current.scrollTop = history.current.scrollHeight; }, [messages]);
  return <section className="room-chat" aria-label="Room chat">
    <ol className="chat-history" ref={history} aria-label="Chat messages" aria-live="polite" aria-relevant="additions">
      {messages.map(message => <li key={message.id}>
        <div className="chat-author"><span className="color-dot" style={{ background: ROOM_COLORS[message.color ?? ""] ?? "#ffffff" }} />
          <strong>{message.name}</strong><time dateTime={new Date(message.sent_at_ms).toISOString()}>
            {new Date(message.sent_at_ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>
        <p>{message.text}</p>
      </li>)}
      {!messages.length && <li className="chat-empty">No messages yet.</li>}
    </ol>
    <form onSubmit={event => { event.preventDefault(); if (text.trim() && send(text)) setText(""); }}>
      <label className="sr-only" htmlFor="room-chat-input">Chat message</label>
      <input id="room-chat-input" value={text} onChange={event => setText(event.target.value)} maxLength={500}
        placeholder="Message your table…" autoComplete="off" disabled={disabled} />
      <button className="game-button" type="submit" disabled={disabled || !text.trim()}>Send</button>
    </form>
  </section>;
}
