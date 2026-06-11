import { useEffect, useRef } from 'react';

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
};

export function TranscriptStream({ messages }: { messages: ChatMessage[] }) {
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!streamRef.current) return;
    streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [messages]);

  return (
    <div
      ref={streamRef}
      className="min-h-[220px] max-h-[360px] space-y-3 overflow-y-auto rounded-lg border border-line bg-white p-3 text-xs leading-5"
    >
      {messages.length === 0 ? (
        <span className="text-faint">Start a test to see the conversation.</span>
      ) : (
        messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[82%] whitespace-pre-wrap rounded-lg px-3 py-2 ${
                message.role === 'user'
                  ? 'bg-primary text-white'
                  : 'border border-line bg-off text-text'
              }`}
            >
              {message.text}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
