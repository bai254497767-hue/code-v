import { Body, Controller, Get, Param, ParseIntPipe, Patch, Post, Query } from "@nestjs/common";
import { AssignLeadDto } from "./dto/assign-lead.dto";
import { CloseLeadDto } from "./dto/close-lead.dto";
import { CreateLeadDto } from "./dto/create-lead.dto";
import { QueryLeadsDto } from "./dto/query-leads.dto";
import { UpdateLeadSalesStageDto } from "./dto/update-lead-sales-stage.dto";
import { UpdateLeadDto } from "./dto/update-lead.dto";
import { LeadsService } from "./leads.service";

@Controller("leads")
export class LeadsController {
  constructor(private readonly leadsService: LeadsService) {}

  @Post()
  create(@Body() dto: CreateLeadDto) {
    return this.leadsService.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryLeadsDto) {
    return this.leadsService.findAll(query);
  }

  @Get(":id")
  findOne(@Param("id", ParseIntPipe) id: number) {
    return this.leadsService.findOne(id);
  }

  @Patch(":id")
  update(@Param("id", ParseIntPipe) id: number, @Body() dto: UpdateLeadDto) {
    return this.leadsService.update(id, dto);
  }

  @Patch(":id/assign")
  assign(@Param("id", ParseIntPipe) id: number, @Body() dto: AssignLeadDto) {
    return this.leadsService.assign(id, dto);
  }

  @Patch(":id/close")
  close(@Param("id", ParseIntPipe) id: number, @Body() dto: CloseLeadDto) {
    return this.leadsService.close(id, dto);
  }

  @Patch(":id/sales-stage")
  updateSalesStage(@Param("id", ParseIntPipe) id: number, @Body() dto: UpdateLeadSalesStageDto) {
    return this.leadsService.updateSalesStage(id, dto);
  }

  @Get(":id/status-histories")
  findStatusHistories(@Param("id", ParseIntPipe) id: number) {
    return this.leadsService.findStatusHistories(id);
  }
}
