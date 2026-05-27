import { Type } from "class-transformer";
import { IsIn, IsInt, IsOptional, IsString, Max, Min } from "class-validator";

export class QueryCustomersDto {
  @IsOptional()
  @IsString()
  keyword?: string;

  @IsOptional()
  @IsString()
  status?: string;

  @IsOptional()
  @IsString()
  source?: string;

  @IsOptional()
  @IsString()
  intended_model?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  owner_id?: number;

  @IsOptional()
  @IsString()
  start_time?: string;

  @IsOptional()
  @IsString()
  end_time?: string;

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
