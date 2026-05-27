import { BadRequestException, Injectable, NotFoundException } from "@nestjs/common";
import { CreateVehicleImageDto } from "./dto/create-vehicle-image.dto";
import { CreateVehicleDto } from "./dto/create-vehicle.dto";
import { QueryVehiclesDto } from "./dto/query-vehicles.dto";
import { UpdateVehicleStatusDto } from "./dto/update-vehicle-status.dto";
import { UpdateVehicleDto } from "./dto/update-vehicle.dto";
import { PaginatedResult, StatusHistory, Vehicle, VehicleImage, VehicleStatus } from "./vehicles.types";

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

    const now = new Date().toISOString();
    const status = (dto.status ?? "on_sale") as VehicleStatus;
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
      status,
      owner_id: dto.owner_id,
      store_id: dto.store_id,
      listed_at: status === "on_sale" ? now : undefined,
      stock_in_at: now,
      sold_at: status === "sold" ? now : undefined,
      created_at: now,
      updated_at: now
    };

    this.vehicles.push(vehicle);
    this.recordStatusHistory(vehicle.id, undefined, status, "车辆入库创建");
    return vehicle;
  }

  findAll(query: QueryVehiclesDto): PaginatedResult<Vehicle> {
    const page = query.page ?? 1;
    const pageSize = Math.min(query.page_size ?? 20, 100);
    const keyword = query.keyword?.trim().toLowerCase();

    const filtered = this.vehicles.filter((vehicle) => {
      const matchesBrand = !query.brand || vehicle.brand.includes(query.brand);
      const matchesModel = !query.model || vehicle.model.includes(query.model) || vehicle.series.includes(query.model);
      const matchesStatus = !query.status || vehicle.status === query.status;
      const matchesMinPrice = query.min_price === undefined || vehicle.sale_price >= query.min_price;
      const matchesMaxPrice = query.max_price === undefined || vehicle.sale_price <= query.max_price;
      const listedAt = vehicle.listed_at ? new Date(vehicle.listed_at).getTime() : undefined;
      const matchesListedFrom = !query.listed_from || (listedAt !== undefined && listedAt >= new Date(query.listed_from).getTime());
      const matchesListedTo = !query.listed_to || (listedAt !== undefined && listedAt <= new Date(query.listed_to).getTime());
      const searchable = [
        vehicle.brand,
        vehicle.series,
        vehicle.model,
        vehicle.color,
        vehicle.plate_number,
        vehicle.vin
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      const matchesKeyword = !keyword || searchable.includes(keyword);

      return (
        matchesBrand &&
        matchesModel &&
        matchesStatus &&
        matchesMinPrice &&
        matchesMaxPrice &&
        matchesListedFrom &&
        matchesListedTo &&
        matchesKeyword
      );
    });

    const sortBy = query.sort_by ?? "created_at";
    const sortOrder = query.sort_order ?? "desc";
    filtered.sort((a, b) => {
      const left = a[sortBy] ?? "";
      const right = b[sortBy] ?? "";
      if (left === right) return 0;
      const result = left > right ? 1 : -1;
      return sortOrder === "asc" ? result : -result;
    });

    const start = (page - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize);

    return {
      items,
      meta: {
        page,
        page_size: pageSize,
        total: filtered.length,
        total_pages: Math.ceil(filtered.length / pageSize)
      }
    };
  }

  getStatistics(): Record<string, unknown> {
    const now = Date.now();
    const statusDistribution = this.vehicles.reduce<Record<string, number>>((acc, vehicle) => {
      acc[vehicle.status] = (acc[vehicle.status] ?? 0) + 1;
      return acc;
    }, {});

    const averageStockDays = this.vehicles.length
      ? Math.round(
          this.vehicles.reduce((sum, vehicle) => {
            const end = vehicle.sold_at ? new Date(vehicle.sold_at).getTime() : now;
            const start = new Date(vehicle.stock_in_at).getTime();
            return sum + Math.max(0, Math.floor((end - start) / 86400000));
          }, 0) / this.vehicles.length
        )
      : 0;

    return {
      total: this.vehicles.length,
      on_sale: statusDistribution.on_sale ?? 0,
      reserved: statusDistribution.reserved ?? 0,
      sold: statusDistribution.sold ?? 0,
      off_shelf: statusDistribution.off_shelf ?? 0,
      status_distribution: statusDistribution,
      average_stock_days: averageStockDays
    };
  }

  findOne(id: number): Vehicle & { images: VehicleImage[]; stock_days: number } {
    const vehicle = this.findVehicle(id);
    const end = vehicle.sold_at ? new Date(vehicle.sold_at).getTime() : Date.now();
    const stockDays = Math.max(0, Math.floor((end - new Date(vehicle.stock_in_at).getTime()) / 86400000));

    return {
      ...vehicle,
      images: this.findImages(id),
      stock_days: stockDays
    };
  }

  update(id: number, dto: UpdateVehicleDto): Vehicle {
    const vehicle = this.findVehicle(id);
    if (dto.vin && dto.vin !== vehicle.vin) {
      this.assertUniqueVin(dto.vin, id);
    }

    Object.assign(vehicle, {
      ...dto,
      configuration: dto.configuration ?? vehicle.configuration,
      updated_at: new Date().toISOString()
    });

    return vehicle;
  }

  updateStatus(id: number, dto: UpdateVehicleStatusDto): Vehicle {
    const vehicle = this.findVehicle(id);
    if (vehicle.status === dto.status) {
      throw new BadRequestException("车辆已处于目标状态");
    }

    const now = new Date().toISOString();
    const previousStatus = vehicle.status;
    vehicle.status = dto.status;
    vehicle.updated_at = now;
    vehicle.listed_at = dto.status === "on_sale" && !vehicle.listed_at ? now : vehicle.listed_at;
    vehicle.sold_at = dto.status === "sold" ? now : undefined;

    this.recordStatusHistory(vehicle.id, previousStatus, dto.status, dto.reason);
    return vehicle;
  }

  remove(id: number): Vehicle {
    return this.updateStatus(id, {
      status: "off_shelf",
      reason: "删除库存车辆，自动下架"
    });
  }

  createImage(vehicleId: number, dto: CreateVehicleImageDto): VehicleImage {
    this.findVehicle(vehicleId);
    const image: VehicleImage = {
      id: this.nextImageId++,
      vehicle_id: vehicleId,
      file_name: dto.file_name,
      file_url: dto.file_url,
      sort_order: dto.sort_order ?? this.images.filter((item) => item.vehicle_id === vehicleId).length,
      uploaded_by: dto.uploaded_by,
      created_at: new Date().toISOString()
    };
    this.images.push(image);
    return image;
  }

  findImages(vehicleId: number): VehicleImage[] {
    this.findVehicle(vehicleId);
    return this.images
      .filter((image) => image.vehicle_id === vehicleId)
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  }

  deleteImage(vehicleId: number, imageId: number): void {
    this.findVehicle(vehicleId);
    const index = this.images.findIndex((image) => image.vehicle_id === vehicleId && image.id === imageId);
    if (index === -1) {
      throw new NotFoundException("车辆图片不存在");
    }
    this.images.splice(index, 1);
  }

  findStatusHistories(vehicleId: number): StatusHistory[] {
    this.findVehicle(vehicleId);
    return this.statusHistories
      .filter((history) => history.target_id === vehicleId)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }

  private findVehicle(id: number): Vehicle {
    const vehicle = this.vehicles.find((item) => item.id === id);
    if (!vehicle) {
      throw new NotFoundException("车辆不存在");
    }
    return vehicle;
  }

  private assertUniqueVin(vin: string, ignoreId?: number): void {
    const exists = this.vehicles.some((vehicle) => vehicle.vin === vin && vehicle.id !== ignoreId);
    if (exists) {
      throw new BadRequestException("VIN码已存在，请检查车辆资料");
    }
  }

  private recordStatusHistory(
    vehicleId: number,
    fromStatus: string | undefined,
    toStatus: string,
    reason?: string
  ): void {
    this.statusHistories.push({
      id: this.nextHistoryId++,
      target_type: "vehicle",
      target_id: vehicleId,
      from_status: fromStatus,
      to_status: toStatus,
      reason,
      created_at: new Date().toISOString()
    });
  }
}
