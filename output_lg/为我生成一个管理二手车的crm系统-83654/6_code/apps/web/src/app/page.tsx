import Link from "next/link";

export default function HomePage() {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <section style={{ width: "100%", maxWidth: 420 }}>
        <h1 style={{ margin: "0 0 12px", fontSize: 28 }}>二手车 CRM 管理后台</h1>
        <p style={{ margin: "0 0 24px", color: "#667085", lineHeight: 1.7 }}>
          项目骨架已就绪，后续模块可在此基础上接入认证、客户、线索、库存与订单功能。
        </p>
        <Link
          href="/login"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: 40,
            padding: "0 16px",
            borderRadius: 6,
            background: "#0f766e",
            color: "#fff",
            fontWeight: 600
          }}
        >
          进入登录页
        </Link>
      </section>
    </main>
  );
}
