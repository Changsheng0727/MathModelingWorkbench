import "./globals.css";

export const metadata = {
  title: "数学建模竞赛智能工作台",
  description: "赛题解析、选题分析、论文骨架生成",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
