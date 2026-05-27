import { Type } from "class-transformer";
import { IsInt, Min } from "class-validator";

export class AssignLeadDto {
  @Type(() => Number)
  @IsInt()
  @Min(1)
  owner_id!: number;
}
