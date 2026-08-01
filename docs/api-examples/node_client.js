/**
 * 能力 API Node.js 示例客户端（M6 / T6-3）
 *
 * 用法：
 *   node node_client.js --key sk-xxxx --base-url http://localhost:8000/api/v1/external
 */

const crypto = require("crypto");

function request(baseUrl, key, path, payload) {
  const url = `${baseUrl}${path}`;
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": key,
    },
    body: JSON.stringify(payload),
  }).then(async (resp) => {
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    }
    return resp.json();
  });
}

/** 订阅方校验 Webhook 签名（HMAC-SHA256）。 */
function verifyWebhook(secret, rawBody, signature) {
  const expected = crypto
    .createHmac("sha256", secret)
    .update(rawBody)
    .digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}

async function main() {
  const args = process.argv.slice(2);
  const key = args[args.indexOf("--key") + 1];
  const baseUrl =
    args[args.indexOf("--base-url") + 1] ||
    "http://localhost:8000/api/v1/external";
  if (!key) {
    console.error("缺少 --key");
    process.exit(1);
  }

  // 1. 简历解析
  const parsed = await request(baseUrl, key, "/resume/parse", {
    content: "张三，5 年后端开发经验，精通 Python / Django / MySQL",
    request_id: "node-demo-1",
  });
  console.log("[resume/parse]", JSON.stringify(parsed).slice(0, 200));

  const resume = (parsed.data) || { skills: ["Python"] };

  // 2. 匹配评估
  const match = await request(baseUrl, key, "/match/evaluate", {
    resume,
    jd: { title: "资深后端工程师", required_skills: ["Python", "Django", "Redis"] },
    request_id: "node-demo-2",
  });
  console.log("[match/evaluate] score =", match.data.match_score);

  // 3. 模拟面试（逐题评分）
  const interview = await request(baseUrl, key, "/interview/simulate", {
    resume,
    jd: { title: "后端工程师" },
    answers: [
      { question: "请简述 Python 中 GIL 的作用", answer: "GIL 使同一时刻仅一个线程执行字节码" },
    ],
    request_id: "node-demo-3",
  });
  console.log(
    "[interview/simulate] evaluations =",
    (interview.data.evaluations || []).length
  );

  console.log("\n全部能力 API 调用成功。Webhook 验签函数见 verifyWebhook()。");
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
