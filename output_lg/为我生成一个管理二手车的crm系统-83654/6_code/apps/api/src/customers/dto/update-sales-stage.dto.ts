import { IsNotEmpty, IsOptional, IsString, MaxLength } from "class-validator";

export class UpdateSalesStageDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(40)
  sales_stage!: string;

  @IsOptional()
  @IsString()
  @MaxLength(200)
  reason?: string;
}
