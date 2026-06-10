export default function NotFound() {
  return (
    <main className="not-found-page">
      <section className="not-found-panel">
        <p className="eyebrow">页面未找到</p>
        <h1>404</h1>
        <p>当前地址没有对应的工作台页面。请返回客户端首页，或重新打开数模方舟客户端。</p>
        <a className="primary compact" href="/">返回工作台</a>
      </section>
    </main>
  );
}
