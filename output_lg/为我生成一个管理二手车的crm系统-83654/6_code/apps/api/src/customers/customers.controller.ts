import { Body, Controller, Delete, Get, Param, ParseIntPipe, Patch, Post, Query } from "@nestjs/common";
import { CustomersService } from "./customers.service";
import { CreateCustomerDto } from "./dto/create-customer.dto";
import { QueryCustomersDto } from "./dto/query-customers.dto";
import { UpdateCustomerDto } from "./dto/update-customer.dto";
import { UpdateSalesStageDto } from "./dto/update-sales-stage.dto";

@Controller("customers")
export class CustomersController {
  constructor(private readonly customersService: CustomersService) {}

  @Post()
  create(@Body() dto: CreateCustomerDto) {
    return this.customersService.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryCustomersDto) {
    return this.customersService.findAll(query);
  }

  @Get(":id")
  findOne(@Param("id", ParseIntPipe) id: number) {
    return this.customersService.findOne(id);
  }

  @Patch(":id")
  update(@Param("id", ParseIntPipe) id: number, @Body() dto: UpdateCustomerDto) {
    return this.customersService.update(id, dto);
  }

  @Delete(":id")
  remove(@Param("id", ParseIntPipe) id: number) {
    return this.customersService.remove(id);
  }

  @Patch(":id/sales-stage")
  updateSalesStage(@Param("id", ParseIntPipe) id: number, @Body() dto: UpdateSalesStageDto) {
    return this.customersService.updateSalesStage(id, dto);
  }

  @Get(":id/stage-histories")
  findStageHistories(@Param("id", ParseIntPipe) id: number) {
    return this.customersService.findStageHistories(id);
  }
}
