export default function LoginPage() {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <form
        style={{
          width: "100%",
          maxWidth: 380,
          display: "grid",
          gap: 16,
          padding: 24,
          border: "1px solid #d9dee8",
          borderRadius: 8,
          background: "#fff"
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 24 }}>账号登录</h1>
          <p style={{ margin: "8px 0 0", color: "#667085" }}>请输入账号信息访问管理后台</p>
        </div>
        <label style={{ display: "grid", gap: 6 }}>
          <span>用户名</span>
          <input name="username" autoComplete="username" style={{ minHeight: 40, border: "1px solid #d9dee8", borderRadius: 6, padding: "0 10px" }} />
        </label>
        <label style={{ display: "grid", gap: 6 }}>
          <span>密码</span>
          <input name="password" type="password" autoComplete="current-password" style={{ minHeight: 40, border: "1px solid #d9dee8", borderRadius: 6, padding: "0 10px" }} />
        </label>
        <button type="button" style={{ minHeight: 42, border: 0, borderRadius: 6, background: "#0f766e", color: "#fff", fontWeight: 600 }}>
          登录
        </button>
      </form>
    </main>
  );
}
