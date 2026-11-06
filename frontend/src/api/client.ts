import axios from 'axios';
import {
  Document,
  QueryRequest,
  QueryResponse,
  SummarizeRequest,
  SummarizeResponse,
  QuizRequest,
  QuizResponse,
  QuizReview,
  StudentProfile,
  Grade,
  AnalyticsOverview,
  AssessmentHistoryItem,
  SubjectAnalytics,
  PerformanceMetric,
  MasteryItem,
  MasteryHistoryItem
  , LearningRecommendation, LearningProgress
  , CurriculumSubject, CurriculumChapter, DocumentStatus
} from '../types';
import { AssessmentAttempt } from '../types';

// Same-origin requests use the dev proxy and keep session cookies on the UI host.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  withCredentials: true,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getMyProfile = async (): Promise<StudentProfile> =>
  (await api.get<StudentProfile>('/students/me')).data;

export const updateMyProfile = async (payload: { display_name?: string; grade_id?: string }): Promise<StudentProfile> =>
  (await api.patch<StudentProfile>('/students/me', payload)).data;

export const listGrades = async (): Promise<Grade[]> => (await api.get<Grade[]>('/auth/grades')).data;
export const listCurriculumSubjects = async (): Promise<CurriculumSubject[]> => (await api.get('/curriculum/subjects')).data;
export const listCurriculumChapters = async (subjectId: string): Promise<CurriculumChapter[]> => (await api.get(`/curriculum/subjects/${subjectId}/chapters`)).data;
export const listAdminGrades = async (): Promise<Grade[]> => (await api.get('/curriculum/admin/grades')).data;
export const listAdminSubjects = async (gradeId: string): Promise<CurriculumSubject[]> => (await api.get(`/curriculum/admin/grades/${gradeId}/subjects`)).data;
export const listAdminChapters = async (subjectId: string): Promise<CurriculumChapter[]> => (await api.get(`/curriculum/admin/subjects/${subjectId}/chapters`)).data;
export const listAssessmentSubjects = async (): Promise<{id:string; name:string}[]> => (await api.get('/assessments/subjects')).data;
export const startDiagnostic = async (subject_id: string): Promise<AssessmentAttempt> => (await api.post('/assessments/diagnostic/start', { subject_id })).data;
export const submitDiagnostic = async (attemptId: string, answers: {attempt_question_id:string; selected_option_id:string}[]): Promise<{accuracy:number}> => (await api.post(`/assessments/attempts/${attemptId}/submit`, { answers })).data;
export const getAnalyticsOverview = async (): Promise<AnalyticsOverview> => (await api.get('/analytics/overview')).data;
export const getSubjectAnalytics = async (subjectId: string): Promise<SubjectAnalytics> => (await api.get(`/analytics/subjects/${subjectId}`)).data;
export const getChapterAnalytics = async (subjectId: string): Promise<PerformanceMetric[]> => (await api.get(`/analytics/subjects/${subjectId}/chapters`)).data;
export const getAssessmentHistory = async (): Promise<AssessmentHistoryItem[]> => (await api.get('/analytics/assessment-history')).data;
export const getPerformanceTrends = async (): Promise<{ points: AssessmentHistoryItem[] }> => (await api.get('/analytics/performance-trends')).data;
export const getMasteryOverview = async (): Promise<MasteryItem[]> => (await api.get('/mastery/overview')).data;
export const getSubjectMastery = async (subjectId: string): Promise<MasteryItem[]> => (await api.get(`/mastery/subjects/${subjectId}`)).data;
export const getTopicMasteryHistory = async (topicId: string): Promise<MasteryHistoryItem[]> => (await api.get(`/mastery/topics/${topicId}/history`)).data;
export const getLearningRecommendations = async (): Promise<LearningRecommendation[]> => (await api.get('/learning/recommendations')).data;
export const getLearningProgress = async (): Promise<LearningProgress[]> => (await api.get('/learning/progress')).data;
export const updateLearningRecommendation = async (id:string, status:string): Promise<LearningRecommendation> => (await api.patch(`/learning/recommendations/${id}`,{status})).data;
export const startReassessment = async (payload:{topic_ids?:string[];chapter_ids?:string[];question_count?:number}): Promise<AssessmentAttempt> => (await api.post('/learning/reassessments/start',payload,{timeout:910_000})).data;

export const getHealth = async () => {
  const response = await api.get('/health/');
  return response.data;
};

export const uploadDocument = async (formData: FormData): Promise<Document> => {
  const response = await api.post<Document>('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 120_000,
  });
  return response.data;
};

export const listDocuments = async (subject?: string, grade?: string, subject_id?: string, chapter_id?: string): Promise<Document[]> => {
  const response = await api.get<Document[]>('/documents/', {
    params: { subject, grade, subject_id, chapter_id }
  });
  return response.data;
};

export const getDocumentStatus = async (documentId: string): Promise<DocumentStatus> => {
  const response = await api.get<DocumentStatus>('/documents/' + documentId + '/status');
  return response.data;
};

export const sendQuery = async (request: QueryRequest): Promise<QueryResponse> => {
  const response = await api.post<QueryResponse>('/query/', request, { timeout: 310_000 });
  return response.data;
};

export const summarizeChapter = async (request: SummarizeRequest): Promise<SummarizeResponse> => {
  const response = await api.post<SummarizeResponse>('/query/summarize', request);
  return response.data;
};

export const generateQuiz = async (request: QuizRequest): Promise<QuizResponse> => {
  const response = await api.post<QuizResponse>('/query/quiz', request, { timeout: 910_000 });
  return response.data;
};

export const getQuizAttempt = async (id: string): Promise<AssessmentAttempt> => (await api.get(`/assessments/attempts/${id}`)).data;
export const getQuizReview = async (id: string): Promise<QuizReview> => (await api.get(`/assessments/attempts/${id}/results`)).data;
