"use client";

interface ChatErrorBannerProps {
  message: string | null;
}

export default function ChatErrorBanner({ message }: ChatErrorBannerProps) {
  if (!message) return null;

  const isKeyError = /API key|DEEPSEEK_API_KEY/i.test(message);

  return (
    <div className="mx-3 mt-2 px-3 py-2 rounded border border-dracula-red/40 bg-dracula-red/10 text-[11px] font-mono text-dracula-red">
      <p className="font-bold mb-1">Turn failed</p>
      <p className="text-dracula-fg/80 break-words">{message}</p>
      {isKeyError && (
        <p className="mt-1 text-dracula-comment">Set DEEPSEEK_API_KEY in .env and restart the backend.</p>
      )}
    </div>
  );
}
