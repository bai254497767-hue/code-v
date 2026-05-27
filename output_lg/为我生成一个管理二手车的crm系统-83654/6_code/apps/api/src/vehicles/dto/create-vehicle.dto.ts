import { Type } from "class-transformer";
import {
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsObject,
  IsOptional,
  IsString,
  Min
} from "class-validator";

export class CreateVehicleDto {
  @IsString()
  @IsNotEmpty()
  brand!: string;

  @IsString()
  @IsNotEmpty()
  series!: string;

  @IsString()
  @IsNotEmpty()
  model!: string;

  @Type(() => Number)
  @IsInt()
  @Min(1900)
  year!: number;

  @Type(() => Number)
  @IsInt()
  @Min(0)
  mileage!: number;

  @IsString()
  @IsOptional()
  color?: string;

  @IsString()
  @IsOptional()
  displacement?: string;

  @IsString()
  @IsOptional()
  plate_number?: string;

  @IsString()
  @IsNotEmpty()
  vin!: string;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  purchase_price!: number;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  sale_price!: number;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  @IsOptional()
  reconditioning_cost?: number;

  @IsObject()
  @IsOptional()
  configuration?: Record<string, unknown>;

  @IsString()
  @IsOptional()
  condition_description?: string;

  @IsString()
  @IsOptional()
  remark?: string;

  @IsString()
  @IsOptional()
  status?: string;

  @Type(() => Number)
  @IsInt()
  @IsOptional()
  owner_id?: number;

  @Type(() => Number)
  @IsInt()
  @IsOptional()
  store_id?: number;
}
