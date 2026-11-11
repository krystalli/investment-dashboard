// Cloudflare Worker：儀表板的「資料代理」。
// 只轉發 Yahoo Finance 的公開行情，而且只接受來自你儀表板網址的瀏覽器請求，所以不是公開代理。
//
// 部署步驟（約 5 分鐘，免費方案足夠）：
//   1. 登入 https://dash.cloudflare.com → Workers & Pages → Create → Create Worker → 取個名字 → Deploy
//   2. 按 Edit code，把預設內容全部換成這個檔案的內容，Deploy
//   3. 複製 Worker 網址（https://xxxx.workers.dev），到儀表板右上角 🔗 →「資料代理」貼上，按「儲存代理」
//
// 介面：GET https://xxxx.workers.dev/?url=<編碼後的 Yahoo 網址>

const ALLOW_HOSTS = ['query1.finance.yahoo.com', 'query2.finance.yahoo.com'];
const ALLOW_ORIGINS = ['https://krystalli.github.io'];

export default {
  async fetch(request) {
    const origin = request.headers.get('Origin') || '';
    const cors = { 'Access-Control-Allow-Origin': origin, 'Vary': 'Origin' };

    if (!ALLOW_ORIGINS.includes(origin)) return new Response('forbidden', { status: 403 });
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: { ...cors, 'Access-Control-Allow-Methods': 'GET', 'Access-Control-Max-Age': '86400' } });
    }
    if (request.method !== 'GET') return new Response('method not allowed', { status: 405, headers: cors });

    let target;
    try { target = new URL(new URL(request.url).searchParams.get('url')); }
    catch (e) { return new Response('bad url', { status: 400, headers: cors }); }
    if (target.protocol !== 'https:' || !ALLOW_HOSTS.includes(target.hostname)) {
      return new Response('host not allowed', { status: 403, headers: cors });
    }

    const upstream = await fetch(target.toString(), {
      headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' },
      cf: { cacheTtl: 300, cacheEverything: true },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { ...cors, 'Content-Type': upstream.headers.get('Content-Type') || 'application/json', 'Cache-Control': 'public, max-age=300' },
    });
  },
};
