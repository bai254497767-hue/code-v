import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  Param,
  ParseIntPipe,
  Patch,
  Post,
  Query
} from "@nestjs/common";
import { CreateVehicleImageDto } from "./dto/create-vehicle-image.dto";
import { CreateVehicleDto } from "./dto/create-vehicle.dto";
import { QueryVehiclesDto } from "./dto/query-vehicles.dto";
import { UpdateVehicleStatusDto } from "./dto/update-vehicle-status.dto";
import { UpdateVehicleDto } from "./dto/update-vehicle.dto";
import { VehiclesService } from "./vehicles.service";

@Controller("vehicles")
export class VehiclesController {
  constructor(private readonly vehiclesService: VehiclesService) {}

  @Post()
  create(@Body() dto: CreateVehicleDto) {
    return this.vehiclesService.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryVehiclesDto) {
    return this.vehiclesService.findAll(query);
  }

  @Get("statistics")
  getStatistics() {
    return this.vehiclesService.getStatistics();
  }

  @Get(":id")
  findOne(@Param("id", ParseIntPipe) id: number) {
    return this.vehiclesService.findOne(id);
  }

  @Patch(":id")
  update(@Param("id", ParseIntPipe) id: number, @Body() dto: UpdateVehicleDto) {
    return this.vehiclesService.update(id, dto);
  }

  @Patch(":id/status")
  updateStatus(@Param("id", ParseIntPipe) id: number, @Body() dto: UpdateVehicleStatusDto) {
    return this.vehiclesService.updateStatus(id, dto);
  }

  @Delete(":id")
  remove(@Param("id", ParseIntPipe) id: number) {
    return this.vehiclesService.remove(id);
  }

  @Post(":id/images")
  createImage(@Param("id", ParseIntPipe) id: number, @Body() dto: CreateVehicleImageDto) {
    return this.vehiclesService.createImage(id, dto);
  }

  @Get(":id/images")
  findImages(@Param("id", ParseIntPipe) id: number) {
    return this.vehiclesService.findImages(id);
  }

  @Delete(":id/images/:image_id")
  @HttpCode(204)
  deleteImage(
    @Param("id", ParseIntPipe) id: number,
    @Param("image_id", ParseIntPipe) imageId: number
  ) {
    this.vehiclesService.deleteImage(id, imageId);
  }

  @Get(":id/status-histories")
  findStatusHistories(@Param("id", ParseIntPipe) id: number) {
    return this.vehiclesService.findStatusHistories(id);
  }
}
