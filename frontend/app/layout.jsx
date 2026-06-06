import "./globals.css";

export const metadata = {
  title: "数模方舟 ModelArk",
  description: "面向数学建模竞赛的本地智能客户端",
};

const themeInitScript = `
(() => {
  try {
    const requested = new URLSearchParams(location.search).get("theme");
    let stored = "";
    try {
      stored = localStorage.getItem("modelark-theme") || "";
    } catch {}
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme =
      requested === "light" || requested === "dark"
        ? requested
        : stored === "light" || stored === "dark"
          ? stored
          : prefersDark ? "dark" : "light";
    if (requested === "light" || requested === "dark") {
      try {
        localStorage.setItem("modelark-theme", requested);
      } catch {}
    }
    document.documentElement.dataset.theme = theme;
  } catch {
    document.documentElement.dataset.theme = "light";
  }
})();
`;

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
