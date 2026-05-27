const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3001/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {})
    },
    credentials: "include"
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const message = typeof payload === "object" && payload !== null && "message" in payload ? String((payload as { message: unknown }).message) : "请求失败";
    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}
