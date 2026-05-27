import { Type } from "class-transformer";
import {
  IsInt,
  IsNotEmpty,
  IsNumber,
  IsObject,
  IsOptional,
  IsString,
  MaxLength,
  Min
} from "class-validator";

export class CreateVehicleDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(80)
  brand!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(80)
  series!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(120)
  model!: string;

  @Type(() => Number)
  @IsInt()
  @Min(1900)
  year!: number;

  @Type(() => Number)
  @IsInt()
  @Min(0)
  mileage!: number;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  color?: string;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  displacement?: string;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  plate_number?: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(40)
  vin!: string;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  purchase_price!: number;

  @Type(() => Number)
  @IsNumber()
  @Min(0)
  sale_price!: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  reconditioning_cost?: number;

  @IsOptional()
  @IsObject()
  configuration?: Record<string, unknown>;

  @IsOptional()
  @IsString()
  condition_description?: string;

  @IsOptional()
  @IsString()
  remark?: string;

  @IsOptional()
  @IsString()
  status?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  owner_id?: number;

  @Type(() => Number)
  @IsInt()
  store_id!: number;

  @IsOptional()
  @Type(() => Date)
  listed_at?: Date;

  @IsOptional()
  @Type(() => Date)
  stock_in_at?: Date;
}
