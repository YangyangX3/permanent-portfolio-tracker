# Web UI (Next.js + React)

本目录为“永久投资组合”网页前端（Next.js + React）。后端使用仓库根目录的 FastAPI 服务；前端通过 Next `rewrites` 代理到后端，浏览器端请求保持同源、无需 CORS。

## 运行

1) 启动后端（在仓库根目录）：

```powershell
python -m uvicorn app.main:app --port 8010
```

2) 启动前端（在本目录）：

```powershell
cd web
copy .env.local.example .env.local
npm install
npm run dev
```

打开：`http://127.0.0.1:3000`

## 环境变量

- `PP_BACKEND_ORIGIN`：后端地址（默认 `http://127.0.0.1:8010`）
