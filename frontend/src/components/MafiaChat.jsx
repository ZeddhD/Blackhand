import { useState } from "react";

export default function MafiaChat({ messages, onSend }) {
  const [text, setText] = useState("");

  const submit = () => {
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <div className="card mafia-chat">
      <h2>🤫 Mafia Channel</h2>
      <div className="chat-log">
        {messages.map((m, i) => (
          <p key={i}>
            <strong>{m.name}:</strong> {m.text}
          </p>
        ))}
      </div>
      <div className="row">
        <input
          placeholder="Message the mafia..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button onClick={submit}>Send</button>
      </div>
    </div>
  );
}
