import { Type } from "class-transformer";
import { IsIn, IsInt, IsNumber, IsOptional, IsString, Min } from "class-validator";

const VEHICLE_SORT_FIELDS = [
  "id",
  "brand",
  "sale_price",
  "listed_at",
  "stock_in_at",
  "created_at",
  "updated_at"
] as const;

export class QueryVehiclesDto {
  @IsString()
  @IsOptional()
  brand?: string;

  @IsString()
  @IsOptional()
  model?: string;

  @IsString()
  @IsOptional()
  status?: string;

  @IsString()
  @IsOptional()
  keyword?: string;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  @IsOptional()
  min_price?: number;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  @IsOptional()
  max_price?: number;

  @IsString()
  @IsOptional()
  listed_from?: string;

  @IsString()
  @IsOptional()
  listed_to?: string;

  @Type(() => Number)
  @IsInt()
  @Min(1)
  @IsOptional()
  page?: number = 1;

  @Type(() => Number)
  @IsInt()
  @Min(1)
  @IsOptional()
  page_size?: number = 20;

  @IsIn(VEHICLE_SORT_FIELDS)
  @IsOptional()
  sort_by?: (typeof VEHICLE_SORT_FIELDS)[number] = "created_at";

  @IsIn(["asc", "desc"])
  @IsOptional()
  sort_order?: "asc" | "desc" = "desc";
}
