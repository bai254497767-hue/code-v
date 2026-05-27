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
  store_id?: number;
  listed_at?: string;
  stock_in_at: string;
  sold_at?: string;
  created_at: string;
  updated_at: string;
}

export interface VehicleImage {
  id: number;
  vehicle_id: number;
  file_name: string;
  file_url: string;
  sort_order: number;
  uploaded_by?: number;
  created_at: string;
}

export interface StatusHistory {
  id: number;
  target_type: "vehicle";
  target_id: number;
  from_status?: string;
  to_status: string;
  reason?: string;
  operator_id?: number;
  created_at: string;
}

export interface PaginatedResult<T> {
  items: T[];
  meta: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}
