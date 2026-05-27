import { Type } from "class-transformer";
import { IsDecimal, IsEnum, IsInt, IsMobilePhone, IsNotEmpty, IsOptional, IsString, MaxLength, Min } from "class-validator";

export enum LeadUrgency {
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high"
}

export class CreateLeadDto {
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  customer_id?: number;

  @IsString()
  @IsNotEmpty()
  @MaxLength(80)
  name!: string;

  @IsMobilePhone("zh-CN")
  mobile!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(40)
  source!: string;

  @IsOptional()
  @IsString()
  @MaxLength(120)
  intended_model?: string;

  @IsOptional()
  @IsDecimal({ decimal_digits: "0,2" })
  budget_min?: string;

  @IsOptional()
  @IsDecimal({ decimal_digits: "0,2" })
  budget_max?: string;

  @IsOptional()
  @IsEnum(LeadUrgency)
  urgency?: LeadUrgency;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  owner_id?: number;

  @Type(() => Number)
  @IsInt()
  @Min(1)
  store_id!: number;
}
