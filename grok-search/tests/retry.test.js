#!/usr/bin/env node
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { requestJson } from "../scripts/lib/providers.js";

const config = { retryMaxAttempts: 3, retryMultiplier: 0, retryMaxWait: 0.05, debug: false };

async function withServer(handler, callback) {
  const server = createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    return await callback(server.address().port);
  } finally {
    server.close();
  }
}

let requests = 0;

// A stable but malformed JSON response must not be retried.
await withServer(
  (req, res) => {
    requests += 1;
    req.resume();
    res.writeHead(200, { "content-type": "application/json" });
    res.end("not json");
  },
  async (port) => {
    await assert.rejects(
      requestJson(`http://127.0.0.1:${port}/`, { headers: {}, body: {}, timeoutMs: 5000, config, retry: true }),
      /不是有效 JSON/
    );
    assert.equal(requests, 1);
  }
);

// Retry-After far beyond retryMaxWait is clamped, not honored verbatim.
requests = 0;
const clampStartedAt = Date.now();
await withServer(
  (req, res) => {
    requests += 1;
    req.resume();
    res.writeHead(429, { "content-type": "text/plain", "retry-after": "3600" });
    res.end("slow down");
  },
  async (port) => {
    await assert.rejects(
      requestJson(`http://127.0.0.1:${port}/`, { headers: {}, body: {}, timeoutMs: 5000, config, retry: true }),
      /HTTP 429/
    );
    assert.equal(requests, 3);
    assert.equal(Date.now() - clampStartedAt < 2000, true);
  }
);

// Timed-out POSTs may still bill server-side; retryOnTimeout=false stops after one attempt.
requests = 0;
await withServer(
  (req) => {
    requests += 1;
    req.resume();
  },
  async (port) => {
    await assert.rejects(
      requestJson(`http://127.0.0.1:${port}/`, {
        headers: {},
        body: {},
        timeoutMs: 200,
        config,
        retry: true,
        retryOnTimeout: false,
      }),
      /请求超时/
    );
    assert.equal(requests, 1);
  }
);

// Default behavior still retries timeouts.
requests = 0;
await withServer(
  (req) => {
    requests += 1;
    req.resume();
  },
  async (port) => {
    await assert.rejects(
      requestJson(`http://127.0.0.1:${port}/`, { headers: {}, body: {}, timeoutMs: 150, config, retry: true }),
      /请求超时/
    );
    assert.equal(requests, 3);
  }
);

console.log("retry fixtures ok");
