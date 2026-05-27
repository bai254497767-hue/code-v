export type VehicleStatus = "on_sale" | "reserved" | "sold" | "off_shelf";

export interface Vehicle {
  id: number;
  brand: string;
  series: string;
  model: string;
  year: number;
  mileage: number;
  color?: string;
  displacement?: string;
  plate_number?: string;
  vin: string;
  purchase_price: number;
  sale_price: number;
  reconditioning_cost: number;
  configuration: Record<string, unknown>;
  condition_description?: string;
  remark?: string;
  status: VehicleStatus;
  owner_id?: number;
  store_id: number;
  listed_at?: Date;
  stock_in_at: Date;
  sold_at?: Date;
  created_at: Date;
  updated_at: Date;
}

export interface VehicleImage {
  id: number;
  vehicle_id: number;
  file_name: string;
  file_url: string;
  sort_order: number;
  uploaded_by?: number;
  created_at: Date;
}

export interface StatusHistory {
  id: number;
  target_type: string;
  target_id: number;
  from_status?: string;
  to_status: string;
  reason?: string;
  operator_id?: number;
  created_at: Date;
}

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
