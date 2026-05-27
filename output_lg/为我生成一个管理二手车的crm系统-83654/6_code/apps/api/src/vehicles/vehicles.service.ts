import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { CreateVehicleImageDto } from "./dto/create-vehicle-image.dto";
import { CreateVehicleDto } from "./dto/create-vehicle.dto";
import { QueryVehiclesDto } from "./dto/query-vehicles.dto";
import { UpdateVehicleStatusDto } from "./dto/update-vehicle-status.dto";
import { UpdateVehicleDto } from "./dto/update-vehicle.dto";
import { PaginatedResult, StatusHistory, Vehicle, VehicleImage, VehicleStatus } from "./vehicles.types";

const VALID_SORT_FIELDS = new Set<keyof Vehicle>([
  "id",
  "brand",
  "series",
  "model",
  "year",
  "mileage",
  "sale_price",
  "status",
  "listed_at",
  "stock_in_at",
  "created_at",
  "updated_at"
]);

@Injectable()
export class VehiclesService {
  private vehicles: Vehicle[] = [];
  private images: VehicleImage[] = [];
  private statusHistories: StatusHistory[] = [];
  private nextVehicleId = 1;
  private nextImageId = 1;
  private nextHistoryId = 1;

  create(dto: CreateVehicleDto): Vehicle {
    this.assertUniqueVin(dto.vin);

    const now = new Date();
    const vehicle: Vehicle = {
      id: this.nextVehicleId++,
      brand: dto.brand,
      series: dto.series,
      model: dto.model,
      year: dto.year,
      mileage: dto.mileage,
      color: dto.color,
      displacement: dto.displacement,
      plate_number: dto.plate_number,
      vin: dto.vin,
      purchase_price: dto.purchase_price,
      sale_price: dto.sale_price,
      reconditioning_cost: dto.reconditioning_cost ?? 0,
      configuration: dto.configuration ?? {},
      condition_description: dto.condition_description,
      remark: dto.remark,
      status: (dto.status as VehicleStatus | undefined) ?? "on_sale",
      owner_id: dto.owner_id,
      store_id: dto.store_id,
      listed_at: dto.listed_at,
      stock_in_at: dto.stock_in_at ?? now,
      sold_at: undefined,
      created_at: now,
      updated_at: now
    };

    this.vehicles.push(vehicle);
    this.recordStatusHistory(vehicle.id, undefined, vehicle.status, "车辆入库", vehicle.owner_id);
    return vehicle;
  }

  findAll(query: QueryVehiclesDto): PaginatedResult<Vehicle> {
    const page = query.page ?? 1;
    const pageSize = query.page_size ?? 20;
    const keyword = query.keyword?.trim().toLowerCase();

    let items = this.vehicles.filter((vehicle) => {
      if (query.brand && !vehicle.brand.includes(query.brand)) return false;
      if (query.model && !vehicle.model.includes(query.model)) return false;
      if (query.status && vehicle.status !== query.status) return false;
      if (query.price_min !== undefined && vehicle.sale_price < query.price_min) return false;
      if (query.price_max !== undefined && vehicle.sale_price > query.price_max) return false;
      if (query.listed_from && (!vehicle.listed_at || vehicle.listed_at < query.listed_from)) return false;
      if (query.listed_to && (!vehicle.listed_at || vehicle.listed_at > query.listed_to)) return false;

      if (!keyword) return true;
      return [vehicle.brand, vehicle.series, vehicle.model, vehicle.color, vehicle.plate_number, vehicle.vin]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });

    const sortBy = VALID_SORT_FIELDS.has(query.sort_by as keyof Vehicle) ? (query.sort_by as keyof Vehicle) : "created_at";
    const direction = query.sort_order === "asc" ? 1 : -1;
    items = [...items].sort((left, right) => this.compareValues(left[sortBy], right[sortBy]) * direction);

    const total = items.length;
    const start = (page - 1) * pageSize;
    return {
      items: items.slice(start, start + pageSize),
      total,
      page,
      page_size: pageSize
    };
  }

  getStatistics(): Record<string, unknown> {
    const now = Date.now();
    const status_distribution = this.vehicles.reduce<Record<string, number>>((result, vehicle) => {
      result[vehicle.status] = (result[vehicle.status] ?? 0) + 1;
      return result;
    }, {});

    const activeVehicles = this.vehicles.filter((vehicle) => vehicle.status !== "sold");
    const totalInventoryDays = activeVehicles.reduce((sum, vehicle) => {
      return sum + Math.max(0, Math.floor((now - vehicle.stock_in_at.getTime()) / 86400000));
    }, 0);

    return {
      total: this.vehicles.length,
      on_sale: status_distribution.on_sale ?? 0,
      reserved: status_distribution.reserved ?? 0,
      sold: status_distribution.sold ?? 0,
      off_shelf: status_distribution.off_shelf ?? 0,
      status_distribution,
      average_inventory_days: activeVehicles.length === 0 ? 0 : Math.round(totalInventoryDays / activeVehicles.length)
    };
  }

  findOne(id: number): Vehicle & { images: VehicleImage[]; inventory_days: number } {
    const vehicle = this.getVehicle(id);
    const endTime = vehicle.sold_at?.getTime() ?? Date.now();
    return {
      ...vehicle,
      images: this.findImages(id),
      inventory_days: Math.max(0, Math.floor((endTime - vehicle.stock_in_at.getTime()) / 86400000))
    };
  }

  update(id: number, dto: UpdateVehicleDto): Vehicle {
    const vehicle = this.getVehicle(id);
    if (dto.vin && dto.vin !== vehicle.vin) {
      this.assertUniqueVin(dto.vin, id);
    }

    Object.assign(vehicle, {
      ...dto,
      configuration: dto.configuration ?? vehicle.configuration,
      updated_at: new Date()
    });

    return vehicle;
  }

  updateStatus(id: number, dto: UpdateVehicleStatusDto): Vehicle {
    const vehicle = this.getVehicle(id);
    const nextStatus = dto.status as VehicleStatus;

    if (vehicle.status === nextStatus) {
      throw new BadRequestException("车辆已经处于该状态");
    }

    const previousStatus = vehicle.status;
    vehicle.status = nextStatus;
    vehicle.updated_at = new Date();
    vehicle.sold_at = nextStatus === "sold" ? new Date() : vehicle.sold_at;
    this.recordStatusHistory(id, previousStatus, nextStatus, dto.reason, vehicle.owner_id);
    return vehicle;
  }

  remove(id: number): Vehicle {
    return this.updateStatus(id, { status: "off_shelf", reason: "下架库存车辆" });
  }

  addImage(vehicleId: number, dto: CreateVehicleImageDto): VehicleImage {
    this.getVehicle(vehicleId);
    const image: VehicleImage = {
      id: this.nextImageId++,
      vehicle_id: vehicleId,
      file_name: dto.file_name,
      file_url: dto.file_url,
      sort_order: dto.sort_order ?? this.images.filter((item) => item.vehicle_id === vehicleId).length,
      uploaded_by: dto.uploaded_by,
      created_at: new Date()
    };
    this.images.push(image);
    return image;
  }

  findImages(vehicleId: number): VehicleImage[] {
    this.getVehicle(vehicleId);
    return this.images
      .filter((image) => image.vehicle_id === vehicleId)
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
  }

  removeImage(vehicleId: number, imageId: number): { deleted: true } {
    this.getVehicle(vehicleId);
    const index = this.images.findIndex((image) => image.vehicle_id === vehicleId && image.id === imageId);
    if (index === -1) {
      throw new NotFoundException("车辆图片不存在");
    }
    this.images.splice(index, 1);
    return { deleted: true };
  }

  findStatusHistories(vehicleId: number): StatusHistory[] {
    this.getVehicle(vehicleId);
    return this.statusHistories
      .filter((history) => history.target_type === "vehicle" && history.target_id === vehicleId)
      .sort((left, right) => right.created_at.getTime() - left.created_at.getTime());
  }

  private getVehicle(id: number): Vehicle {
    const vehicle = this.vehicles.find((item) => item.id === id);
    if (!vehicle) {
      throw new NotFoundException("车辆不存在");
    }
    return vehicle;
  }

  private assertUniqueVin(vin: string, ignoredId?: number): void {
    const duplicated = this.vehicles.some((vehicle) => vehicle.vin === vin && vehicle.id !== ignoredId);
    if (duplicated) {
      throw new BadRequestException("VIN码已存在，请检查车辆信息");
    }
  }

  private recordStatusHistory(
    vehicleId: number,
    fromStatus: string | undefined,
    toStatus: string,
    reason?: string,
    operatorId?: number
  ): void {
    this.statusHistories.push({
      id: this.nextHistoryId++,
      target_type: "vehicle",
      target_id: vehicleId,
      from_status: fromStatus,
      to_status: toStatus,
      reason,
      operator_id: operatorId,
      created_at: new Date()
    });
  }

  private compareValues(left: unknown, right: unknown): number {
    if (left === right) return 0;
    if (left === undefined || left === null) return -1;
    if (right === undefined || right === null) return 1;
    if (left instanceof Date && right instanceof Date) return left.getTime() - right.getTime();
    if (typeof left === "number" && typeof right === "number") return left - right;
    return String(left).localeCompare(String(right), "zh-Hans-CN");
  }
}
