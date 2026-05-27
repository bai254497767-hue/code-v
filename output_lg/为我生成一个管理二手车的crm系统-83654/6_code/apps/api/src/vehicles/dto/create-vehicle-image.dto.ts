import { Type } from "class-transformer";
import { IsInt, IsNotEmpty, IsOptional, IsString, MaxLength, Min } from "class-validator";

export class CreateVehicleImageDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(180)
  file_name!: string;

  @IsString()
  @IsNotEmpty()
  file_url!: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  sort_order?: number;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  uploaded_by?: number;
}
