const express = require("express");
const client = require("prom-client");

const app = express();
app.use(express.json());

// ── Prometheus metrics setup ──────────────────
const register = new client.Registry();
client.collectDefaultMetrics({ register });

const httpRequestCounter = new client.Counter({
  name: "http_requests_total",
  help: "Total HTTP requests",
  labelNames: ["method", "route", "status"],
  registers: [register],
});

const httpLatency = new client.Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request latency",
  labelNames: ["method", "route"],
  buckets: [0.1, 0.5, 1, 2, 5],
  registers: [register],
});

// ── Middleware: track every request ──────────
app.use((req, res, next) => {
  const end = httpLatency.startTimer({ method: req.method, route: req.path });
  res.on("finish", () => {
    httpRequestCounter.inc({ method: req.method, route: req.path, status: res.statusCode });
    end();
  });
  next();
});

// ── Normal API routes ─────────────────────────
app.get("/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

app.get("/api/products", (req, res) => {
  res.json([{ id: 1, name: "Widget A" }, { id: 2, name: "Widget B" }]);
});

app.post("/api/orders", (req, res) => {
  res.json({ id: Math.floor(Math.random() * 1000), status: "created" });
});

// ── Metrics endpoint (Prometheus scrapes this) 
app.get("/metrics", async (req, res) => {
  res.set("Content-Type", register.contentType);
  res.send(await register.metrics());
});

// ── Simulate routes (for demos) ───────────────
app.get("/simulate/cpu-spike", (req, res) => {
  console.error("[SIMULATE] CPU spike triggered");
  const end = Date.now() + 15000; // burn CPU for 15 seconds
  while (Date.now() < end) { Math.sqrt(Math.random()); }
  res.json({ simulated: "cpu-spike", duration: "15s" });
});

app.get("/simulate/memory-leak", (req, res) => {
  console.error("[SIMULATE] Memory leak triggered");
  global._leak = global._leak || [];
  for (let i = 0; i < 100000; i++) {
    global._leak.push({ data: new Array(1000).fill("leak") });
  }
  res.json({ simulated: "memory-leak", heapMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024) });
});

app.get("/simulate/crash", (req, res) => {
  console.error("[SIMULATE] Crash triggered — process will exit");
  res.json({ simulated: "crash" });
  setTimeout(() => process.exit(1), 500);
});

app.get("/simulate/error-flood", (req, res) => {
  for (let i = 0; i < 20; i++) {
    console.error(`[ERROR] Simulated error #${i} - connection pool exhausted`);
  }
  res.json({ simulated: "error-flood", errors: 20 });
});

// ── Start server ──────────────────────────────
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`[sample-app] running on port ${PORT}`);
});