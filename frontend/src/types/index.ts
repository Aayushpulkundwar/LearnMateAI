export interface Citation {
  chunk_id?: string;
  document_id: string;
  document_title: string;
  chapter?: string;
  grade_id?: string;
  subject_id?: string;
  chapter_id?: string;
  page_number?: number;
  chunk_index?: number;
  source_index?: number;
  similarity_score?: number;
  snippet: string;
}

export interface Document {
  id: string;
  title: string;
  subject?: string;
  grade?: string;
  chapter?: string;
  grade_id?: string;
  subject_id?: string;
  chapter_id?: string;
  processing_status: 'pending' | 'processing' | 'completed' | 'failed';
  heartbeat_at?: string;
  minio_path: string;
  created_at: string;
}
export interface DocumentStatus { id: string; processing_status: Document['processing_status']; heartbeat_at?: string; created_at: string; }

export interface QueryRequest {
  question: string;
  document_id?: string;
  subject?: string;
  grade?: string;
  chapter?: string;
  grade_id?: string;
  subject_id?: string;
  chapter_id?: string;
  study_topic_id?: string;
  explanation_depth?: 'brief' | 'standard' | 'detailed';
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

export interface QuizRequest {
  document_id?: string;
  subject_id?: string;
  chapter_id?: string;
  chapter?: string;
  num_questions?: number;
  difficulty?: 'easy' | 'medium' | 'hard';
  topic_id?: string;
}

export type QuizResponse = AssessmentAttempt;
export interface QuizReview {
  result: { total_questions: number; correct: number; incorrect: number; unanswered: number; accuracy: number };
  questions: { id: string; question_text: string; selected_option_id: string | null;
    options: { id: string; option_text: string; is_correct: boolean }[];
    explanation: string | null; source_document_id: string | null; source_chunk_id: string | null;
    source_page: number | null; source_title: string | null; chapter_name: string | null;
    difficulty?: string; question_type?: string; bloom_level?: string; concept?: string; topic_id?: string;
    source_chunk_ids?: string[]; evidence?: string }[];
}

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  isRefused?: boolean;
  timestamp: string;
}

export interface StudentProfile {
  id: string;
  user_id: string;
  email: string;
  display_name?: string;
  grade_id: string;
  grade_name: string;
  is_admin: boolean;
}

export interface AuthResponse {
  student: StudentProfile;
}

export interface Grade {
  id: string;
  name: string;
}
export interface CurriculumSubject { id: string; name: string; }
export interface CurriculumChapter { id: string; name: string; chapter_number: number; }
export interface AssessmentOption { id: string; option_text: string; }
export interface AssessmentQuestion { difficulty?: 'easy' | 'medium' | 'hard'; question_type?: string; concept?: string; id: string; question_text: string; display_order: number; options: AssessmentOption[]; }
export interface AssessmentAttempt { id: string; status: string; score?: number; coverage_warning?: string; questions: AssessmentQuestion[]; }

export interface PerformanceMetric {
  id: string;
  correct: number;
  total_questions: number;
  attempt_count: number;
  accuracy: number;
  classification: string;
  evidence_sufficient: boolean;
  provisional: boolean;
}

export interface SubjectOverview extends PerformanceMetric { subject_id: string; }
export interface AnalyticsOverview { subjects: SubjectOverview[]; total_attempts: number; }
export interface SubjectAnalytics {
  subject_id: string;
  overall: PerformanceMetric | null;
  strongest_chapters: PerformanceMetric[];
  weakest_chapters: PerformanceMetric[];
  frequently_incorrect_topics: PerformanceMetric[];
}
export interface AssessmentHistoryItem {
  attempt_id: string;
  subject_id: string;
  submitted_at: string;
  accuracy: number;
  total_questions: number;
}
export interface MasteryItem {
  topic_id: string;
  topic_name: string;
  chapter_id: string;
  chapter_name: string;
  subject_id: string;
  subject_name: string;
  mastery_score: number;
  evidence_count: number;
  confidence_level: string;
  classification: 'Strong' | 'Developing' | 'Needs Improvement' | 'Insufficient Evidence';
  last_assessed_at: string | null;
  provisional: boolean;
  weighted_evidence?: number | null;
  evidence_interval_low?: number | null;
  evidence_interval_high?: number | null;
  interval_note?: string | null;
}
export interface MasteryHistoryItem {
  previous_score: number;
  updated_score: number;
  recorded_at: string;
  assessment_attempt_id: string | null;
}
export interface LearningRecommendation { id:string; topic_id:string; topic_name:string; chapter_name:string; subject_name:string; priority:'high'|'medium'|'low'; recommendation_type:string; reason:string; action:'study'|'practice'|'reassess'; status:string; }
export interface LearningProgress { topic_id:string; topic_name:string; current_mastery:number; previous_mastery:number | null; change:number | null; direction:string; }
