import { Type } from "class-transformer";
import { IsIn, IsInt, IsOptional, IsString, Min } from "class-validator";

export class QueryVehiclesDto {
  @IsOptional()
  @IsString()
  brand?: string;

  @IsOptional()
  @IsString()
  model?: string;

  @IsOptional()
  @IsString()
  status?: string;

  @IsOptional()
  @IsString()
  keyword?: string;

  @IsOptional()
  @Type(() => Number)
  @Min(0)
  price_min?: number;

  @IsOptional()
  @Type(() => Number)
  @Min(0)
  price_max?: number;

  @IsOptional()
  @Type(() => Date)
  listed_from?: Date;

  @IsOptional()
  @Type(() => Date)
  listed_to?: Date;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page = 1;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page_size = 20;

  @IsOptional()
  @IsString()
  sort_by = "created_at";

  @IsOptional()
  @IsIn(["asc", "desc"])
  sort_order: "asc" | "desc" = "desc";
}
