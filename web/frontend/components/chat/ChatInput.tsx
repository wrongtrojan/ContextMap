"use client";

import { useState } from "react";
import { Send } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  return (
    <form onSubmit={handleSubmit} className="p-3 border-t border-dracula-comment/20 flex gap-2">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        placeholder="Ask about your assets..."
        className="flex-1 bg-dracula-bg border border-dracula-comment/30 rounded px-3 py-2 text-sm text-dracula-fg placeholder:text-dracula-comment focus:outline-none focus:border-dracula-purple disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled || !text.trim()}
        className="px-3 py-2 bg-dracula-purple/30 border border-dracula-purple/50 rounded text-dracula-purple hover:bg-dracula-purple/40 disabled:opacity-30 transition-colors"
      >
        <Send size={16} />
      </button>
    </form>
  );
}
