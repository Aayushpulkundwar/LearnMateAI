import axios from 'axios';
import {
  Document,
  QueryRequest,
  QueryResponse,
  SummarizeRequest,
  SummarizeResponse,
  QuizRequest,
  QuizResponse
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getHealth = async () => {
  const response = await api.get('/health/');
  return response.data;
};

export const uploadDocument = async (formData: FormData): Promise<Document> => {
  const response = await api.post<Document>('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const listDocuments = async (subject?: string, grade?: string): Promise<Document[]> => {
  const response = await api.get<Document[]>('/documents/', {
    params: { subject, grade }
  });
  return response.data;
};

export const getDocumentStatus = async (documentId: string): Promise<Document> => {
  const response = await api.get<Document>(`/documents/${documentId}/status`);
  return response.data;
};

export const sendQuery = async (request: QueryRequest): Promise<QueryResponse> => {
  const response = await api.post<QueryResponse>('/query/', request);
  return response.data;
};

export const summarizeChapter = async (request: SummarizeRequest): Promise<SummarizeResponse> => {
  const response = await api.post<SummarizeResponse>('/query/summarize', request);
  return response.data;
};

export const generateQuiz = async (request: QuizRequest): Promise<QuizResponse> => {
  const response = await api.post<QuizResponse>('/query/quiz', request);
  return response.data;
};
