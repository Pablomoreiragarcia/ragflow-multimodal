// frontend/src/lib/types.ts

export type Attachment = {
  id: string;
  kind: "image" | "table" | string;
  path: string;
  title?: string | null;
  mime_type?: string | null;
  meta?: any;
  created_at?: string | null;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
  image_path?: string | null;
  table_path?: string | null;
  attachments?: Attachment[];
};

export type ConversationDetail = {
  id: string;
  title: string | null;
  scope: string | null;
  model?: string | null;
  top_k?: number | null;
  doc_ids?: string[];
  deleted: boolean;
  created_at: string;
  updated_at: string;
  messages: Message[];
};

export type AskResponse = {
  answer: string;
  context: any[];
  conversation_id?: string | null;
  assistant_message_id?: string | null;
  attachments?: { kind: string; path: string; title?: string | null }[];
};

export type DocumentItem = {
  id: string;
  original_filename?: string | null;
  status: "pending" | "processing" | "ready" | "failed" | string;
  updated_at?: string;
};