import React from 'react';
import { Message } from '../types';
import { CitationBadge } from './CitationBadge';
import { User, Bot, AlertTriangle } from 'lucide-react';

interface MessageThreadProps {
  messages: Message[];
  isLoading: boolean;
}

export const MessageThread: React.FC<MessageThreadProps> = ({ messages, isLoading }) => {
  return (
    <div className="message-thread">
      {messages.length === 0 ? (
        <div className="empty-chat">
          <Bot size={48} className="empty-icon" />
          <h3>Ask your AI Textbook Tutor</h3>
          <p>
            Answers are sourced strictly from your prescribed NCERT / State Board textbooks with page-level citations.
          </p>
        </div>
      ) : (
        messages.map((msg) => (
          <div key={msg.id} className={`message-bubble ${msg.sender}`}>
            <div className="avatar">
              {msg.sender === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className="message-content">
              <div className="message-header">
                <span className="sender-name">
                  {msg.sender === 'user' ? 'Student' : 'Textbook Tutor'}
                </span>
                <span className="timestamp">{msg.timestamp}</span>
              </div>

              {msg.isRefused ? (
                <div className="refusal-box">
                  <AlertTriangle size={18} className="warning-icon" />
                  <p>{msg.content}</p>
                </div>
              ) : (
                <p className="body-text">{msg.content}</p>
              )}

              {msg.citations && msg.citations.length > 0 && (
                <CitationBadge citations={msg.citations} />
              )}
            </div>
          </div>
        ))
      )}

      {isLoading && (
        <div className="message-bubble assistant loading">
          <div className="avatar"><Bot size={18} /></div>
          <div className="message-content">
            <span className="sender-name">Textbook Tutor</span>
            <p className="typing-indicator">Searching prescribed textbook chunks...</p>
          </div>
        </div>
      )}
    </div>
  );
};
