import { Type } from "class-transformer";
import { IsDecimal, IsInt, IsNotEmpty, IsOptional, IsString, MaxLength } from "class-validator";

export class CreateCustomerDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(80)
  name!: string;

  @IsString()
  @IsNotEmpty()
  @MaxLength(30)
  mobile!: string;

  @IsOptional()
  @IsString()
  @MaxLength(80)
  wechat?: string;

  @IsOptional()
  @IsString()
  @MaxLength(60)
  source?: string;

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
  @IsString()
  @MaxLength(40)
  status?: string;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  sales_stage?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  owner_id?: number;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  store_id?: number;
}
