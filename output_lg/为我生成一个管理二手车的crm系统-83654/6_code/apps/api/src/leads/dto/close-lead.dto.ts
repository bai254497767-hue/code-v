import { IsNotEmpty, IsString, MaxLength } from "class-validator";

export class CloseLeadDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  closed_reason!: string;
}
