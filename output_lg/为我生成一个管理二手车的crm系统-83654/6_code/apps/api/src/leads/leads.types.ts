export type LeadStatus = "new" | "assigned" | "following" | "converted" | "closed";

export interface Lead {
  id: number;
  customer_id?: number;
  name: string;
  mobile: string;
  source: string;
  intended_model?: string;
  budget_min?: string;
  budget_max?: string;
  urgency: "low" | "medium" | "high";
  status: LeadStatus;
  sales_stage: string;
  owner_id?: number;
  store_id: number;
  closed_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface StatusHistory {
  id: number;
  target_type: "lead";
  target_id: number;
  from_status?: string;
  to_status: string;
  reason?: string;
  operator_id?: number;
  created_at: string;
}

export interface SalesStageHistory {
  id: number;
  target_type: "lead";
  target_id: number;
  from_stage?: string;
  to_stage: string;
  reason?: string;
  operator_id?: number;
  created_at: string;
}

export interface FollowUpSummary {
  id: number;
  target_type: "lead";
  target_id: number;
  method: string;
  followed_at: string;
  content: string;
  feedback?: string;
  next_follow_up_at?: string;
  created_by?: number;
  created_at: string;
}

export interface PaginatedResult<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
