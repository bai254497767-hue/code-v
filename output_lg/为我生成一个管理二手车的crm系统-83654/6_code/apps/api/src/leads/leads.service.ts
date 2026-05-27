import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { AssignLeadDto } from "./dto/assign-lead.dto";
import { CloseLeadDto } from "./dto/close-lead.dto";
import { CreateLeadDto } from "./dto/create-lead.dto";
import { QueryLeadsDto } from "./dto/query-leads.dto";
import { UpdateLeadSalesStageDto } from "./dto/update-lead-sales-stage.dto";
import { UpdateLeadDto } from "./dto/update-lead.dto";
import { FollowUpSummary, Lead, PaginatedResult, SalesStageHistory, StatusHistory } from "./leads.types";

@Injectable()
export class LeadsService {
  private leads: Lead[] = [];
  private statusHistories: StatusHistory[] = [];
  private salesStageHistories: SalesStageHistory[] = [];
  private followUps: FollowUpSummary[] = [];
  private leadId = 1;
  private statusHistoryId = 1;
  private salesStageHistoryId = 1;

  create(dto: CreateLeadDto): Lead {
    const duplicated = this.leads.some(
      (lead) => lead.mobile === dto.mobile && lead.status !== "closed"
    );

    if (duplicated) {
      throw new BadRequestException("该手机号已存在未关闭销售线索");
    }

    const now = new Date().toISOString();
    const lead: Lead = {
      id: this.leadId++,
      customer_id: dto.customer_id,
      name: dto.name,
      mobile: dto.mobile,
      source: dto.source,
      intended_model: dto.intended_model,
      budget_min: dto.budget_min,
      budget_max: dto.budget_max,
      urgency: dto.urgency ?? "medium",
      status: dto.owner_id ? "assigned" : "new",
      sales_stage: "initial_contact",
      owner_id: dto.owner_id,
      store_id: dto.store_id,
      created_at: now,
      updated_at: now
    };

    this.leads.unshift(lead);
    this.recordStatusHistory(lead.id, undefined, lead.status, "创建销售线索");
    this.recordSalesStageHistory(lead.id, undefined, lead.sales_stage, "初始化销售阶段");
    return lead;
  }

  findAll(query: QueryLeadsDto): PaginatedResult<Lead> {
    const page = query.page ?? 1;
    const pageSize = query.page_size ?? 20;
    const keyword = query.keyword?.trim().toLowerCase();

    let items = this.leads.filter((lead) => {
      const matchedKeyword = !keyword || [lead.name, lead.mobile, lead.intended_model, lead.source]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
      const createdAt = new Date(lead.created_at).getTime();
      const from = query.created_from ? new Date(query.created_from).getTime() : undefined;
      const to = query.created_to ? new Date(query.created_to).getTime() : undefined;

      return matchedKeyword
        && (!query.source || lead.source === query.source)
        && (!query.status || lead.status === query.status)
        && (!query.sales_stage || lead.sales_stage === query.sales_stage)
        && (!query.owner_id || lead.owner_id === query.owner_id)
        && (!query.store_id || lead.store_id === query.store_id)
        && (!from || createdAt >= from)
        && (!to || createdAt <= to);
    });

    items = this.sort(items, query.sort_by ?? "created_at", query.sort_order ?? "desc");
    const total = items.length;
    const start = (page - 1) * pageSize;

    return {
      items: items.slice(start, start + pageSize),
      page,
      page_size: pageSize,
      total,
      total_pages: Math.ceil(total / pageSize)
    };
  }

  findOne(id: number): Lead & { recent_follow_up?: FollowUpSummary; status_histories: StatusHistory[] } {
    const lead = this.findLeadOrFail(id);
    const statusHistories = this.statusHistories.filter((item) => item.target_id === id);
    const recentFollowUp = this.followUps
      .filter((item) => item.target_id === id)
      .sort((a, b) => new Date(b.followed_at).getTime() - new Date(a.followed_at).getTime())[0];

    return {
      ...lead,
      recent_follow_up: recentFollowUp,
      status_histories: statusHistories
    };
  }

  update(id: number, dto: UpdateLeadDto): Lead {
    const lead = this.findLeadOrFail(id);
    const updated: Lead = {
      ...lead,
      ...dto,
      updated_at: new Date().toISOString()
    };

    this.leads = this.leads.map((item) => item.id === id ? updated : item);
    return updated;
  }

  assign(id: number, dto: AssignLeadDto): Lead {
    const lead = this.findLeadOrFail(id);
    const fromStatus = lead.status;
    const nextStatus = lead.status === "new" ? "assigned" : lead.status;
    const updated: Lead = {
      ...lead,
      owner_id: dto.owner_id,
      status: nextStatus,
      updated_at: new Date().toISOString()
    };

    this.leads = this.leads.map((item) => item.id === id ? updated : item);
    if (fromStatus !== nextStatus) {
      this.recordStatusHistory(id, fromStatus, nextStatus, "分配销售线索", dto.owner_id);
    }
    return updated;
  }

  close(id: number, dto: CloseLeadDto): Lead {
    const lead = this.findLeadOrFail(id);
    if (lead.status === "closed") {
      throw new BadRequestException("销售线索已关闭");
    }

    const updated: Lead = {
      ...lead,
      status: "closed",
      closed_reason: dto.closed_reason,
      updated_at: new Date().toISOString()
    };

    this.leads = this.leads.map((item) => item.id === id ? updated : item);
    this.recordStatusHistory(id, lead.status, "closed", dto.closed_reason, lead.owner_id);
    return updated;
  }

  updateSalesStage(id: number, dto: UpdateLeadSalesStageDto): Lead {
    const lead = this.findLeadOrFail(id);
    if (lead.sales_stage === dto.sales_stage) {
      return lead;
    }

    const updated: Lead = {
      ...lead,
      sales_stage: dto.sales_stage,
      status: lead.status === "assigned" ? "following" : lead.status,
      updated_at: new Date().toISOString()
    };

    this.leads = this.leads.map((item) => item.id === id ? updated : item);
    this.recordSalesStageHistory(id, lead.sales_stage, dto.sales_stage, dto.reason, lead.owner_id);
    if (lead.status !== updated.status) {
      this.recordStatusHistory(id, lead.status, updated.status, "推进销售阶段", lead.owner_id);
    }
    return updated;
  }

  findStatusHistories(id: number): StatusHistory[] {
    this.findLeadOrFail(id);
    return this.statusHistories.filter((item) => item.target_id === id);
  }

  private findLeadOrFail(id: number): Lead {
    const lead = this.leads.find((item) => item.id === id);
    if (!lead) {
      throw new NotFoundException("销售线索不存在");
    }
    return lead;
  }

  private recordStatusHistory(
    targetId: number,
    fromStatus: string | undefined,
    toStatus: string,
    reason?: string,
    operatorId?: number
  ): void {
    this.statusHistories.unshift({
      id: this.statusHistoryId++,
      target_type: "lead",
      target_id: targetId,
      from_status: fromStatus,
      to_status: toStatus,
      reason,
      operator_id: operatorId,
      created_at: new Date().toISOString()
    });
  }

  private recordSalesStageHistory(
    targetId: number,
    fromStage: string | undefined,
    toStage: string,
    reason?: string,
    operatorId?: number
  ): void {
    this.salesStageHistories.unshift({
      id: this.salesStageHistoryId++,
      target_type: "lead",
      target_id: targetId,
      from_stage: fromStage,
      to_stage: toStage,
      reason,
      operator_id: operatorId,
      created_at: new Date().toISOString()
    });
  }

  private sort(items: Lead[], sortBy: string, sortOrder: "asc" | "desc"): Lead[] {
    const allowedFields = new Set(["id", "name", "source", "status", "sales_stage", "created_at", "updated_at"]);
    const field = allowedFields.has(sortBy) ? sortBy : "created_at";
    const direction = sortOrder === "asc" ? 1 : -1;

    return [...items].sort((a, b) => {
      const left = a[field as keyof Lead];
      const right = b[field as keyof Lead];
      return String(left ?? "").localeCompare(String(right ?? "")) * direction;
    });
  }
}
