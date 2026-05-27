import { Type } from "class-transformer";
import { IsDateString, IsIn, IsInt, IsOptional, IsString, Max, Min } from "class-validator";

export class QueryLeadsDto {
  @IsOptional()
  @IsString()
  keyword?: string;

  @IsOptional()
  @IsString()
  source?: string;

  @IsOptional()
  @IsString()
  status?: string;

  @IsOptional()
  @IsString()
  sales_stage?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  owner_id?: number;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  store_id?: number;

  @IsOptional()
  @IsDateString()
  created_from?: string;

  @IsOptional()
  @IsDateString()
  created_to?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page = 1;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  page_size = 20;

  @IsOptional()
  @IsString()
  sort_by = "created_at";

  @IsOptional()
  @IsIn(["asc", "desc"])
  sort_order: "asc" | "desc" = "desc";
}
