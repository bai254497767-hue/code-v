import { IsIn, IsOptional, IsString } from "class-validator";

export class UpdateVehicleStatusDto {
  @IsIn(["on_sale", "reserved", "sold", "off_shelf"])
  status!: "on_sale" | "reserved" | "sold" | "off_shelf";

  @IsString()
  @IsOptional()
  reason?: string;
}
