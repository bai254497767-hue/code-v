import Link from "next/link";

type CustomerDetail = {
  id: number;
  name: string;
  mobile: string;
  wechat?: string;
  source?: string;
  intended_model?: string;
  budget_min?: string;
  budget_max?: string;
  status: string;
  sales_stage: string;
  owner_id?: number;
  store_id?: number;
  last_follow_up_at?: string;
  created_at: string;
  updated_at: string;
  recent_follow_ups: unknown[];
};

type StageHistory = {
  id: number;
  from_stage: string;
  to_stage: string;
  reason?: string;
  created_at: string;
};

async function getCustomer(id: string): Promise<CustomerDetail | null> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3001/api/v1";
  try {
    const response = await fetch(`${apiBaseUrl}/customers/${id}`, { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

async function getStageHistories(id: string): Promise<StageHistory[]> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3001/api/v1";
  try {
    const response = await fetch(`${apiBaseUrl}/customers/${id}/stage-histories`, { cache: "no-store" });
    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

export default async function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [customer, histories] = await Promise.all([getCustomer(id), getStageHistories(id)]);

  if (!customer) {
    return (
      <main className="page-shell">
        <Link href="/customers" className="text-link">返回客户列表</Link>
        <section className="empty-state">客户不存在或已删除</section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="page-header">
        <div>
          <p className="eyebrow">客户详情</p>
          <h1>{customer.name}</h1>
          <p className="muted">{customer.mobile} · {customer.intended_model ?? "未填写意向车型"}</p>
        </div>
        <Link className="secondary-button" href="/customers">返回列表</Link>
      </section>

      <section className="detail-grid">
        <div className="panel">
          <h2>基础资料</h2>
          <dl>
            <dt>微信</dt><dd>{customer.wechat ?? "-"}</dd>
            <dt>来源</dt><dd>{customer.source ?? "-"}</dd>
            <dt>状态</dt><dd>{customer.status}</dd>
            <dt>销售阶段</dt><dd>{customer.sales_stage}</dd>
            <dt>负责人</dt><dd>{customer.owner_id ?? "-"}</dd>
            <dt>门店</dt><dd>{customer.store_id ?? "-"}</dd>
          </dl>
        </div>

        <div className="panel">
          <h2>购车意向</h2>
          <dl>
            <dt>意向车型</dt><dd>{customer.intended_model ?? "-"}</dd>
            <dt>预算下限</dt><dd>{customer.budget_min ?? "-"}</dd>
            <dt>预算上限</dt><dd>{customer.budget_max ?? "-"}</dd>
            <dt>最近跟进</dt><dd>{customer.last_follow_up_at ?? "暂无"}</dd>
          </dl>
        </div>
      </section>

      <section className="panel">
        <h2>销售阶段历史</h2>
        {histories.length === 0 ? (
          <p className="muted">暂无阶段变更记录</p>
        ) : (
          <ul className="timeline">
            {histories.map((history) => (
              <li key={history.id}>
                <strong>{history.from_stage} → {history.to_stage}</strong>
                <span>{new Date(history.created_at).toLocaleString("zh-CN")}</span>
                {history.reason ? <p>{history.reason}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
