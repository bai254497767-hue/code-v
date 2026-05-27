import Link from "next/link";

type Customer = {
  id: number;
  name: string;
  mobile: string;
  source?: string;
  intended_model?: string;
  budget_min?: string;
  budget_max?: string;
  status: string;
  sales_stage: string;
  owner_id?: number;
  created_at: string;
};

async function getCustomers(): Promise<{ items: Customer[]; total: number }> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3001/api/v1";
  try {
    const response = await fetch(`${apiBaseUrl}/customers`, { cache: "no-store" });
    if (!response.ok) {
      return { items: [], total: 0 };
    }
    return response.json();
  } catch {
    return { items: [], total: 0 };
  }
}

export default async function CustomerListPage() {
  const data = await getCustomers();

  return (
    <main className="page-shell">
      <section className="page-header">
        <div>
          <p className="eyebrow">客户管理</p>
          <h1>客户列表</h1>
          <p className="muted">集中管理潜在客户、意向车型、预算范围和销售阶段。</p>
        </div>
        <Link className="primary-button" href="/customers/new">
          新增客户
        </Link>
      </section>

      <section className="toolbar">
        <input placeholder="搜索姓名、手机号、微信或意向车型" aria-label="搜索客户" />
        <select aria-label="客户状态">
          <option value="">全部状态</option>
          <option value="active">跟进中</option>
          <option value="deal">已成交</option>
          <option value="lost">已流失</option>
        </select>
        <select aria-label="客户来源">
          <option value="">全部来源</option>
          <option value="manual">手工录入</option>
          <option value="phone">电话咨询</option>
          <option value="online">线上渠道</option>
          <option value="referral">转介绍</option>
        </select>
      </section>

      <section className="table-card">
        <div className="table-title">共 {data.total} 位客户</div>
        <table>
          <thead>
            <tr>
              <th>客户</th>
              <th>手机号</th>
              <th>来源</th>
              <th>意向车型</th>
              <th>预算</th>
              <th>销售阶段</th>
              <th>状态</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {data.items.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-cell">
                  暂无客户数据
                </td>
              </tr>
            ) : (
              data.items.map((customer) => (
                <tr key={customer.id}>
                  <td>
                    <Link href={`/customers/${customer.id}`}>{customer.name}</Link>
                  </td>
                  <td>{customer.mobile}</td>
                  <td>{customer.source ?? "-"}</td>
                  <td>{customer.intended_model ?? "-"}</td>
                  <td>
                    {customer.budget_min || customer.budget_max
                      ? `${customer.budget_min ?? "不限"} - ${customer.budget_max ?? "不限"}`
                      : "-"}
                  </td>
                  <td>{customer.sales_stage}</td>
                  <td>{customer.status}</td>
                  <td>{new Date(customer.created_at).toLocaleDateString("zh-CN")}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
