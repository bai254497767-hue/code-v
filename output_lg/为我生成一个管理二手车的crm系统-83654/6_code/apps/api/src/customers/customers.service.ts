import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { CreateCustomerDto } from "./dto/create-customer.dto";
import { QueryCustomersDto } from "./dto/query-customers.dto";
import { UpdateCustomerDto } from "./dto/update-customer.dto";
import { UpdateSalesStageDto } from "./dto/update-sales-stage.dto";
import { Customer, SalesStageHistory } from "./customers.types";

const SORTABLE_FIELDS = new Set<keyof Customer>([
  "id",
  "name",
  "mobile",
  "source",
  "status",
  "sales_stage",
  "owner_id",
  "store_id",
  "created_at",
  "updated_at",
  "last_follow_up_at"
]);

@Injectable()
export class CustomersService {
  private customers: Customer[] = [];
  private stageHistories: SalesStageHistory[] = [];
  private nextCustomerId = 1;
  private nextStageHistoryId = 1;

  create(dto: CreateCustomerDto): Customer {
    this.assertUniqueMobile(dto.mobile);

    const now = new Date().toISOString();
    const customer: Customer = {
      id: this.nextCustomerId++,
      name: dto.name.trim(),
      mobile: dto.mobile.trim(),
      wechat: dto.wechat?.trim(),
      source: dto.source?.trim(),
      intended_model: dto.intended_model?.trim(),
      budget_min: dto.budget_min,
      budget_max: dto.budget_max,
      status: dto.status ?? "potential",
      sales_stage: dto.sales_stage ?? "initial_contact",
      owner_id: dto.owner_id,
      store_id: dto.store_id,
      created_at: now,
      updated_at: now
    };

    this.customers.push(customer);
    return customer;
  }

  findAll(query: QueryCustomersDto): { items: Customer[]; total: number; page: number; page_size: number } {
    const page = query.page ?? 1;
    const pageSize = query.page_size ?? 20;
    const sortBy = SORTABLE_FIELDS.has(query.sort_by as keyof Customer) ? (query.sort_by as keyof Customer) : "created_at";
    const sortOrder = query.sort_order ?? "desc";

    let items = this.customers.filter((customer) => !customer.deleted_at);

    if (query.keyword) {
      const keyword = query.keyword.trim().toLowerCase();
      items = items.filter((customer) =>
        [customer.name, customer.mobile, customer.wechat, customer.intended_model]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(keyword))
      );
    }

    if (query.status) {
      items = items.filter((customer) => customer.status === query.status);
    }

    if (query.source) {
      items = items.filter((customer) => customer.source === query.source);
    }

    if (query.intended_model) {
      items = items.filter((customer) => customer.intended_model?.includes(query.intended_model ?? ""));
    }

    if (query.owner_id) {
      items = items.filter((customer) => customer.owner_id === query.owner_id);
    }

    if (query.start_time) {
      const start = new Date(query.start_time).getTime();
      items = items.filter((customer) => new Date(customer.created_at).getTime() >= start);
    }

    if (query.end_time) {
      const end = new Date(query.end_time).getTime();
      items = items.filter((customer) => new Date(customer.created_at).getTime() <= end);
    }

    items = [...items].sort((a, b) => {
      const left = a[sortBy];
      const right = b[sortBy];
      if (left === right) return 0;
      if (left === undefined || left === null) return 1;
      if (right === undefined || right === null) return -1;
      const result = left > right ? 1 : -1;
      return sortOrder === "asc" ? result : -result;
    });

    const total = items.length;
    const startIndex = (page - 1) * pageSize;
    return {
      items: items.slice(startIndex, startIndex + pageSize),
      total,
      page,
      page_size: pageSize
    };
  }

  findOne(id: number): Customer & { stage_histories: SalesStageHistory[] } {
    const customer = this.getActiveCustomer(id);
    return {
      ...customer,
      stage_histories: this.stageHistories.filter((history) => history.target_id === id)
    };
  }

  update(id: number, dto: UpdateCustomerDto): Customer {
    const customer = this.getActiveCustomer(id);

    if (dto.mobile && dto.mobile !== customer.mobile) {
      this.assertUniqueMobile(dto.mobile, id);
    }

    Object.assign(customer, {
      ...dto,
      name: dto.name?.trim() ?? customer.name,
      mobile: dto.mobile?.trim() ?? customer.mobile,
      wechat: dto.wechat?.trim(),
      source: dto.source?.trim(),
      intended_model: dto.intended_model?.trim(),
      updated_at: new Date().toISOString()
    });

    return customer;
  }

  remove(id: number): { success: true } {
    const customer = this.getActiveCustomer(id);
    const now = new Date().toISOString();
    customer.deleted_at = now;
    customer.updated_at = now;
    return { success: true };
  }

  updateSalesStage(id: number, dto: UpdateSalesStageDto): Customer {
    const customer = this.getActiveCustomer(id);
    const fromStage = customer.sales_stage;

    if (fromStage === dto.sales_stage) {
      return customer;
    }

    customer.sales_stage = dto.sales_stage;
    customer.updated_at = new Date().toISOString();
    this.stageHistories.push({
      id: this.nextStageHistoryId++,
      target_type: "customer",
      target_id: customer.id,
      from_stage: fromStage,
      to_stage: dto.sales_stage,
      reason: dto.reason,
      created_at: new Date().toISOString()
    });

    return customer;
  }

  findStageHistories(id: number): SalesStageHistory[] {
    this.getActiveCustomer(id);
    return this.stageHistories.filter((history) => history.target_id === id);
  }

  private getActiveCustomer(id: number): Customer {
    const customer = this.customers.find((item) => item.id === id && !item.deleted_at);
    if (!customer) {
      throw new NotFoundException("客户不存在或已删除");
    }
    return customer;
  }

  private assertUniqueMobile(mobile: string, ignoreId?: number): void {
    const duplicated = this.customers.some(
      (customer) => !customer.deleted_at && customer.mobile === mobile.trim() && customer.id !== ignoreId
    );
    if (duplicated) {
      throw new BadRequestException("手机号已存在，请勿重复创建客户");
    }
  }
}
