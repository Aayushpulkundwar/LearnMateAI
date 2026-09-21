import React, { useState } from 'react';
import { Citation } from '../types';
import { Bookmark, FileText, ChevronDown, ChevronUp } from 'lucide-react';

interface CitationBadgeProps {
  citations: Citation[];
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({ citations }) => {
  const [expanded, setExpanded] = useState(false);

  if (!citations || citations.length === 0) return null;

  return (
    <div className="citation-container">
      <button
        onClick={() => setExpanded(!expanded)}
        className="citation-toggle-btn"
      >
        <Bookmark className="icon" size={14} />
        <span>{citations.length} Textbook Citation{citations.length > 1 ? 's' : ''} Attached</span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {expanded && (
        <div className="citation-list">
          {citations.map((cite, idx) => {
            const relevanceText = typeof cite.similarity_score === 'number'
              && Number.isFinite(cite.similarity_score)
              ? `Relevance: ${(cite.similarity_score * 100).toFixed(1)}%`
              : null;

            return (
              <div key={idx} className="citation-card">
                <div className="citation-header">
                  <FileText size={14} className="icon" />
                  <span className="citation-book">{cite.document_title}</span>
                  {cite.chapter && <span className="citation-chapter">• Chapter: {cite.chapter}</span>}
                  {cite.page_number && <span className="citation-page">• Page {cite.page_number}</span>}
                  {relevanceText && (
                    <span
                      className="citation-relevance"
                      title="Semantic similarity between your question and this textbook passage."
                    >
                      • {relevanceText}
                    </span>
                  )}
                </div>
                <p className="citation-snippet">"{cite.snippet}"</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
