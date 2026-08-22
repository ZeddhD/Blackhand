import { useState } from "react";

export default function HandChat({ messages, onSend }) {
  const [text, setText] = useState("");

  const submit = () => {
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <div className="card hand-chat">
      <h2>The Black Hand</h2>
      <div className="chat-log">
        {messages.map((m, i) => (
          <p key={i}>
            <strong>{m.name}:</strong> {m.text}
          </p>
        ))}
      </div>
      <div className="row">
        <input
          placeholder="Message the Hand..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button type="button" className="primary" onClick={submit}>
          Send
        </button>
      </div>
    </div>
  );
}
