import React, { useState, useEffect } from 'react';
import { BookSelector } from './components/BookSelector';
import { MessageThread } from './components/MessageThread';
import { DocumentUpload } from './components/DocumentUpload';
import { listDocuments, sendQuery, summarizeChapter, generateQuiz } from './api/client';
import { Document, Message } from './types';
import { BookOpen, Send, Sparkles, HelpCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | undefined>();
  const [selectedSubject, setSelectedSubject] = useState<string | undefined>();
  const [selectedGrade, setSelectedGrade] = useState<string | undefined>();
  const [selectedChapter, setSelectedChapter] = useState<string | undefined>();

  const [inputQuestion, setInputQuestion] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadDocuments = async () => {
    try {
      const docs = await listDocuments(selectedSubject, selectedGrade);
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [selectedSubject, selectedGrade]);

  const handleSendQuestion = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputQuestion.trim() || isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: 'user',
      content: inputQuestion,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    const currentQ = inputQuestion;
    setInputQuestion('');
    setIsLoading(true);

    try {
      const res = await sendQuery({
        question: currentQ,
        document_id: selectedDocId,
        subject: selectedSubject,
        grade: selectedGrade,
        chapter: selectedChapter,
      });

      const tutorMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        content: res.answer,
        citations: res.citations,
        isRefused: res.is_refused,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, tutorMsg]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        content: err.response?.data?.detail || 'Error communicating with AI Textbook Tutor backend.',
        isRefused: true,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSummarize = async () => {
    if (!selectedDocId) {
      alert('Please select a textbook document from the left sidebar first.');
      return;
    }
    setIsLoading(true);
    try {
      const res = await summarizeChapter({
        document_id: selectedDocId,
        chapter: selectedChapter,
      });

      const msg: Message = {
        id: Date.now().toString(),
        sender: 'assistant',
        content: `📖 Chapter Summary:\n\n${res.summary}\n\nKey Takeaways:\n` + res.key_takeaways.map((t) => `• ${t}`).join('\n'),
        citations: res.citations,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, msg]);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Summarization failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuiz = async () => {
    if (!selectedDocId) {
      alert('Please select a textbook document from the left sidebar first.');
      return;
    }
    setIsLoading(true);
    try {
      const res = await generateQuiz({
        document_id: selectedDocId,
        chapter: selectedChapter,
        num_questions: 5,
      });

      const quizBody = res.questions
        .map(
          (q, i) =>
            `Q${i + 1}: ${q.question}\n` +
            q.options.map((opt, idx) => `  ${String.fromCharCode(65 + idx)}) ${opt}`).join('\n') +
            `\nExplanation: ${q.explanation}`
        )
        .join('\n\n');

      const msg: Message = {
        id: Date.now().toString(),
        sender: 'assistant',
        content: `📝 Practice Quiz:\n\n${quizBody}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, msg]);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Quiz generation failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-brand">
          <BookOpen size={24} className="brand-icon" />
          <h1 className="brand-title">LearnMateAI</h1>
          <span className="brand-badge">NCERT & State Board RAG</span>
        </div>
      </header>

      <div className="main-layout">
        <aside className="sidebar">
          <BookSelector
            documents={documents}
            selectedDocId={selectedDocId}
            selectedSubject={selectedSubject}
            selectedGrade={selectedGrade}
            selectedChapter={selectedChapter}
            onDocChange={setSelectedDocId}
            onSubjectChange={setSelectedSubject}
            onGradeChange={setSelectedGrade}
            onChapterChange={setSelectedChapter}
          />
          <DocumentUpload onUploadSuccess={loadDocuments} />
        </aside>

        <main className="chat-section">
          <MessageThread messages={messages} isLoading={isLoading} />

          <div className="input-section">
            <form onSubmit={handleSendQuestion} className="input-form">
              <input
                type="text"
                placeholder="Ask any question from your prescribed textbook..."
                value={inputQuestion}
                onChange={(e) => setInputQuestion(e.target.value)}
                className="chat-input"
              />
              <button type="submit" disabled={isLoading || !inputQuestion.trim()} className="send-btn">
                <Send size={18} />
              </button>
            </form>

            <div className="secondary-actions">
              <button onClick={handleSummarize} className="action-chip">
                <Sparkles size={14} /> Summarize Chapter
              </button>
              <button onClick={handleQuiz} className="action-chip">
                <HelpCircle size={14} /> Generate Quiz
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
