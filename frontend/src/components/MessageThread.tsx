import React, { useEffect, useLayoutEffect, useRef } from 'react';
import type { ConversationEntry, QuizEntry } from '../state/tutorConversation';
import { CitationBadge } from './CitationBadge';
import { User, Bot, AlertTriangle } from 'lucide-react';

interface MessageThreadProps {
  entries: ConversationEntry[]; followRequest: number; chatLoading: boolean;
  onRetry: (id: string) => void; renderQuiz: (entry: QuizEntry) => React.ReactNode;
}
export const isNearConversationBottom = (scrollHeight: number, clientHeight: number, scrollTop: number) => scrollHeight - clientHeight - scrollTop <= 80;
const useConversationLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

const inlineMarkdown = (text: string) => text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part);
const MarkdownMessage: React.FC<{ content: string }> = ({ content }) => <div className="body-text">{content.split('\n').map((line, index) => {
  const key = `${index}-${line}`;
  if (/^#{1,3}\s/.test(line)) return <strong key={key} className="markdown-heading">{inlineMarkdown(line.replace(/^#{1,3}\s/, ''))}</strong>;
  if (/^[•*-]\s/.test(line)) return <div key={key} className="markdown-list-item">• {inlineMarkdown(line.replace(/^[•*-]\s/, ''))}</div>;
  return <React.Fragment key={key}>{inlineMarkdown(line)}{index < content.split('\n').length - 1 && <br />}</React.Fragment>;
})}</div>;

export const MessageThread: React.FC<MessageThreadProps> = ({ entries, followRequest, chatLoading, onRetry, renderQuiz }) => {
  const container = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const previousRequest = useRef(followRequest);
  const follow = () => {
    if (following.current && container.current) container.current.scrollTop = container.current.scrollHeight;
  };
  useConversationLayoutEffect(() => {
    if (previousRequest.current !== followRequest) {
      following.current = true; // Sending explicitly returns to the current conversation.
      previousRequest.current = followRequest;
    }
    follow();
  }, [entries, followRequest]);
  useConversationLayoutEffect(() => {
    if (!content.current || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(follow);
    observer.observe(content.current);
    return () => observer.disconnect();
  }, []);
  return <div className="message-thread" ref={container} role="log" aria-label="Tutor conversation"
    onScroll={event => { const node = event.currentTarget; following.current = isNearConversationBottom(node.scrollHeight, node.clientHeight, node.scrollTop); }}
    onPointerDownCapture={event => { if ((event.target as HTMLElement).closest?.('.tutor-quiz')) following.current = false; }}>
    <div ref={content}>
      {entries.length === 0 && <div className="empty-chat"><Bot size={48} className="empty-icon" /><h3>Ask LearnMateAI</h3><p>Answers are sourced strictly from your prescribed NCERT / State Board textbooks with page-level citations.</p></div>}
      {entries.map(entry => {
        if (entry.kind === 'quiz') return <React.Fragment key={entry.id}>{renderQuiz(entry)}</React.Fragment>;
        const msg = entry.message;
        return <div key={entry.id} className={`message-bubble ${msg.sender}`}>
          <div className="avatar">{msg.sender === 'user' ? <User size={18} /> : <Bot size={18} />}</div>
          <div className="message-content">
            <div className="message-header"><span className="sender-name">{msg.sender === 'user' ? 'Student' : 'Textbook Tutor'}</span><span className="timestamp">{msg.timestamp}</span></div>
            {entry.pending ? <p className="typing-indicator" role="status">{msg.content}</p> : msg.isRefused ? <div className="refusal-box"><AlertTriangle size={18} className="warning-icon" /><p>{msg.content}</p></div> : <MarkdownMessage content={msg.content} />}
            {msg.citations && msg.citations.length > 0 && <CitationBadge citations={msg.citations} />}
            {!entry.pending && entry.retry && <button type="button" className="text-button" disabled={chatLoading} onClick={() => onRetry(entry.id)}>Retry response</button>}
          </div>
        </div>;
      })}
    </div>
  </div>;
};
