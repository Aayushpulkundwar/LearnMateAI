export interface Citation {
  document_id: string;
  document_title: string;
  chapter?: string;
  page_number?: number;
  snippet: string;
}

export interface Document {
  id: string;
  title: string;
  subject?: string;
  grade?: string;
  chapter?: string;
  processing_status: 'pending' | 'processing' | 'completed' | 'failed';
  heartbeat_at?: string;
  minio_path: string;
  created_at: string;
}

export interface QueryRequest {
  question: string;
  document_id?: string;
  subject?: string;
  grade?: string;
  chapter?: string;
}

export interface QueryResponse {
  question: string;
  answer: string;
  citations: Citation[];
  is_refused: boolean;
  refusal_reason?: string;
}

export interface SummarizeRequest {
  document_id: string;
  chapter?: string;
}

export interface SummarizeResponse {
  document_id: string;
  chapter?: string;
  summary: string;
  key_takeaways: string[];
  citations: Citation[];
}

export interface QuizQuestion {
  question: string;
  options: string[];
  correct_option_index: number;
  explanation: string;
  citation?: Citation;
}

export interface QuizRequest {
  document_id: string;
  chapter?: string;
  num_questions?: number;
}

export interface QuizResponse {
  document_id: string;
  chapter?: string;
  questions: QuizQuestion[];
}

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  isRefused?: boolean;
  timestamp: string;
}
