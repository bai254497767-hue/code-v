import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "二手车 CRM 管理后台",
  description: "客户、线索、库存、订单与权限管理后台"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
