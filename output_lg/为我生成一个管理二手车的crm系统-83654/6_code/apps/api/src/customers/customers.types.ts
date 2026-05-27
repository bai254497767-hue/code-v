export interface Customer {
  id: number;
  name: string;
  mobile: string;
  wechat?: string;
  source?: string;
  intended_model?: string;
  budget_min?: string;
  budget_max?: string;
  status: string;
  sales_stage: string;
  owner_id?: number;
  store_id?: number;
  last_follow_up_at?: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string;
}

export interface SalesStageHistory {
  id: number;
  target_type: "customer";
  target_id: number;
  from_stage: string;
  to_stage: string;
  reason?: string;
  operator_id?: number;
  created_at: string;
}
