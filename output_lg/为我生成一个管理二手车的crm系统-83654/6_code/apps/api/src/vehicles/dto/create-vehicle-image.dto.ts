import { Type } from "class-transformer";
import { IsInt, IsNotEmpty, IsOptional, IsString, Min } from "class-validator";

export class CreateVehicleImageDto {
  @IsString()
  @IsNotEmpty()
  file_name!: string;

  @IsString()
  @IsNotEmpty()
  file_url!: string;

  @Type(() => Number)
  @IsInt()
  @Min(0)
  @IsOptional()
  sort_order?: number;

  @Type(() => Number)
  @IsInt()
  @IsOptional()
  uploaded_by?: number;
}
