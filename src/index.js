#!/usr/bin/env node

/**
 * easystudy-mcp — 超星/学习通 MCP server
 *
 * Provides 8 tools for Chaoxing MOOC platform automation.
 * Designed to be used with Claude Code, Cowork, or any MCP client.
 *
 * npx usage: npx easystudy-mcp
 * Claude Code config:
 *   {
 *     "mcpServers": {
 *       "easystudy": {
 *         "command": "npx",
 *         "args": ["easystudy-mcp"]
 *       }
 *     }
 *   }
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import crypto from "node:crypto";
import process from "node:process";

// ─── Constants ────────────────────────────────────────────────────────────

const DES_KEY = "u2oh6Vu^";
const LOGIN_URL = "https://passport2.chaoxing.com/fanyalogin";
const BASE_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) " +
    "AppleWebKit/537.36 (KHTML, like Gecko) " +
    "Chrome/120.0.0.0 Mobile Safari/537.36",
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "zh-CN,zh;q=0.9",
};

// ─── Session state ────────────────────────────────────────────────────────

const session = {
  loggedIn: false,
  phone: "",
  cookies: {},
  /** Fetch wrapper that carries cookies */
  async fetch(url, opts = {}) {
    const headers = { ...BASE_HEADERS, ...(opts.headers || {}) };
    if (this.cookies) {
      const ck = Object.entries(this.cookies).map(([k, v]) => `${k}=${v}`).join("; ");
      headers["Cookie"] = ck;
    }
    const res = await fetch(url, { ...opts, headers, redirect: "follow" });
    const setCookie = res.headers.get("set-cookie");
    if (setCookie) {
      for (const part of setCookie.split(",")) {
        const m = part.match(/^([^=]+)=([^;]+)/);
        if (m) this.cookies[m[1].trim()] = m[2].trim();
      }
    }
    return res;
  },
};

// ─── DES encryption (same as Chaoxing's Android login) ────────────────────

// Chaoxing uses DES in CBC mode with PKCS5 padding, key = IV = "u2oh6Vu^"
// The password is encrypted and hex-encoded.
function desEncrypt(plaintext) {
  const key = Buffer.from(DES_KEY, "utf8"); // 8 bytes
  const iv = Buffer.from(DES_KEY, "utf8");

  // PKCS5 padding
  const blockSize = 8;
  const padLen = blockSize - (plaintext.length % blockSize);
  const padded = Buffer.concat([
    Buffer.from(plaintext, "utf8"),
    Buffer.alloc(padLen, padLen),
  ]);

  const cipher = crypto.createCipheriv("des-cbc", key, iv);
  cipher.setAutoPadding(false); // we already padded
  const encrypted = Buffer.concat([cipher.update(padded), cipher.final()]);
  return encrypted.toString("hex");
}

// ─── URL helpers ──────────────────────────────────────────────────────────

const urls = {
  coursePage(cid, clid) {
    return `https://mooc1-1.chaoxing.com/mooc-ans/visit/stucoursemiddle?courseid=${cid}&clazzid=${clid}&vc=1&ismooc2=1`;
  },
  homeworkList(cid, clid) {
    return `https://mooc1.chaoxing.com/mooc2/work/list?courseId=${cid}&classId=${clid}`;
  },
  dowork(cid, clid, wid) {
    return `https://mooc1.chaoxing.com/mooc2/work/dowork?courseId=${cid}&classId=${clid}&workId=${wid}&answerId=&workRelationId=&enc=`;
  },
  viewWork(cid, clid, wid) {
    return `https://mooc1.chaoxing.com/mooc2/work/view?courseId=${cid}&classId=${clid}&workId=${wid}`;
  },
  materials(cid, clid) {
    return `https://mooc1.chaoxing.com/coursedata?courseId=${cid}&classId=${clid}`;
  },
  study(cid, clid) {
    return `https://mooc1.chaoxing.com/mycourse/studentstudy?courseId=${cid}&clazzid=${clid}&mooc2=1`;
  },
};

// ─── Tool definitions ─────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "login",
    description:
      "Login to 超星/学习通 (Chaoxing) with phone + password. " +
      "Must call this first. Session cookie is stored automatically. " +
      "Args: phone, password. Returns {success, message}.",
    inputSchema: {
      type: "object",
      properties: {
        phone: { type: "string", description: "Registered phone number" },
        password: { type: "string", description: "Plaintext password" },
      },
      required: ["phone", "password"],
    },
  },
  {
    name: "get_courses",
    description:
      "Get enrolled course list on 超星. Returns a URL + JS extract script " +
      "for use with Chrome DevTools MCP or browser automation. " +
      "HOW: navigate_page → take_snapshot OR evaluate_script with extract_js. " +
      "NEXT: pass courseId+classId to get_homeworks.",
    inputSchema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_homeworks",
    description:
      "Get homework list for a course. Returns browser operation steps: " +
      "navigate to course home → click '作业' tab → take snapshot. " +
      "Shows: title, status (待批阅/未交/已完成/待互评), deadline. " +
      "Extract workId from onclick attributes. " +
      "Args: courseId, classId. NEXT: pass workId to get_homework.",
    inputSchema: {
      type: "object",
      properties: {
        courseId: { type: "string", description: "Course ID from get_courses" },
        classId: { type: "string", description: "Class ID from get_courses" },
      },
      required: ["courseId", "classId"],
    },
  },
  {
    name: "get_homework",
    description:
      "Open a homework page and read all questions on 超星. " +
      "Question types: 0=单选(single), 1=多选(multi), 3=判断(true/false), " +
      "4=简答(essay), 7=计算题(calculation). " +
      "MCQ fill: click .answerBg[data='X']. Text fill: UE.getEditor('answer{id}').setContent(html). " +
      "Submit: btnBlueSubmit() then submitCheckTimes(). " +
      "Args: courseId, classId, workId. NEXT: submit_homework.",
    inputSchema: {
      type: "object",
      properties: {
        courseId: { type: "string" },
        classId: { type: "string" },
        workId: { type: "string", description: "Homework ID from get_homeworks" },
      },
      required: ["courseId", "classId", "workId"],
    },
  },
  {
    name: "submit_homework",
    description:
      "Submit homework answers on 超星 via browser automation. " +
      "Answers format: {'question_index': 'value'}. " +
      "MCQ/TF: 'A'/'B'/'C'/'D' or 'true'/'false'. Essay: HTML string. " +
      "Flow: navigate → fill each answer → btnBlueSubmit() → submitCheckTimes(). " +
      "Args: courseId, classId, workId, answers. NEXT: get_homework_score.",
    inputSchema: {
      type: "object",
      properties: {
        courseId: { type: "string" },
        classId: { type: "string" },
        workId: { type: "string" },
        answers: {
          type: "object",
          description: "Answer map. MCQ: 'A'/'B'/'C'/'D'. TF: 'true'/'false'. Essay: full text.",
        },
        token: { type: "string", description: "Optional page token" },
        enc: { type: "string", description: "Optional enc param" },
      },
      required: ["courseId", "classId", "workId", "answers"],
    },
  },
  {
    name: "get_homework_score",
    description:
      "View homework grading results on 超星. " +
      "HOW: navigate → take_snapshot. Shows correct answers, your answers, " +
      "per-question scores, total score. Green check = correct, red cross = wrong. " +
      "Status: 待批阅=ungraded, 已完成=graded. " +
      "Args: courseId, classId, workId.",
    inputSchema: {
      type: "object",
      properties: {
        courseId: { type: "string" },
        classId: { type: "string" },
        workId: { type: "string" },
      },
      required: ["courseId", "classId", "workId"],
    },
  },
  {
    name: "auto_study",
    description:
      "Auto-complete course task points on 超星: videos, quizzes, PDFs. " +
      "Iterates .ans-job-icon in study iframe, skips .ans-job-finished. " +
      "video→mute+speed play; quiz→parse+fill+submit; pdf→scroll. " +
      "Settings: autoVideo(default true), autoQuiz(default true), " +
      "playbackRate(default 2, max 4), answerInterval(default 3s). " +
      "WARNING: high playback rates may be detected. " +
      "Args: courseId, classId. No login required.",
    inputSchema: {
      type: "object",
      properties: {
        courseId: { type: "string" },
        classId: { type: "string" },
        autoVideo: { type: "boolean", description: "Auto-play videos (default true)" },
        autoAudio: { type: "boolean", description: "Auto-play audio (default false)" },
        autoQuiz: { type: "boolean", description: "Auto-solve quizzes (default true)" },
        autoSubmit: { type: "boolean", description: "Auto-submit quizzes (default true)" },
        autoJump: { type: "boolean", description: "Auto-advance chapters (DANGER, default false)" },
        answerInterval: { type: "number", description: "Seconds between answers (default 3)" },
        playbackRate: { type: "number", description: "Video speed (default 2, max 4)" },
        minAccuracy: { type: "number", description: "Min accuracy to auto-submit (default 0.6)" },
      },
      required: ["courseId", "classId"],
    },
  },
  {
    name: "download_materials",
    description:
      "Download course materials (PPT/PDF/Word/Excel/video) from 超星. " +
      "HOW: navigate course home → click '资料' tab → take_snapshot → click download links. " +
      "Args: courseId, classId.",
    inputSchema: {
      type: "object",
      properties: {
        courseId: { type: "string" },
        classId: { type: "string" },
      },
      required: ["courseId", "classId"],
    },
  },
];

// ─── Action handlers ──────────────────────────────────────────────────────

function checkLogin() {
  if (!session.loggedIn) {
    return { error: "Bitte zuerst login aufrufen / Please call login first" };
  }
  return null;
}

async function handleLogin(args) {
  const { phone, password } = args;
  session.phone = phone;
  const pwdHex = desEncrypt(password);

  const payload = new URLSearchParams({
    fid: "-1",
    uname: phone,
    password: pwdHex,
    refer: "https://i.chaoxing.com",
    t: "true",
    forbidotherlogin: "0",
    validate: "",
    doubleFactorLogin: "0",
    independentId: "0",
  });

  const res = await session.fetch("https://passport2.chaoxing.com/login?newversion=true");

  const loginRes = await session.fetch(LOGIN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: payload.toString(),
  });

  const text = await loginRes.text();
  let result;
  try {
    const data = JSON.parse(text);
    if (data.status) {
      session.loggedIn = true;
      result = { success: true, message: "登录成功 / Login successful" };
    } else {
      result = { success: false, message: data.msg2 || "登录失败" };
    }
  } catch {
    if (text.includes("登录成功") || text.includes("/space/index")) {
      session.loggedIn = true;
      result = { success: true, message: "登录成功 / Login successful" };
    } else if (text.includes("密码错误")) {
      result = { success: false, message: "密码错误 / Wrong password" };
    } else if (text.includes("验证码")) {
      result = { success: false, message: "需要验证码，请稍后重试 / CAPTCHA required" };
    } else {
      result = { success: false, message: "未知错误 / Unknown error" };
    }
  }
  return result;
}

function handleGetCourses(_args) {
  const url = "https://mooc1-1.chaoxing.com/visit/interaction?courseType=1&courseFolderId=0";
  return {
    goal: "获取所有已选课程 / Get all enrolled courses",
    step1: { action: "navigate_page", url },
    step2: { action: "take_snapshot", desc: "查看课程名称、教师、courseId/clazzid" },
    step2_alt: {
      action: "evaluate_script",
      desc: "执行 JS 提取结构化数据",
      js:
        "()=>{var cs=[];" +
        "document.querySelectorAll('a[href*=\"courseid=\"]').forEach(function(a){" +
        "var m=a.href.match(/courseid=(\\d+).*?clazzid=(\\d+)/);" +
        "if(m)cs.push({courseId:m[1],classId:m[2],name:a.textContent.trim()});" +
        "});return cs;}",
    },
    output: "每门课: {courseId, classId, name}",
    next: "get_homeworks(取 courseId, classId)",
  };
}

function handleGetHomeworks(args) {
  const { courseId, classId } = args;
  return {
    goal: "获取课程作业列表 / Get homework list",
    step1: { action: "navigate_page", url: urls.coursePage(courseId, classId) },
    step2: { action: "take_snapshot, click '作业' tab" },
    step3: {
      action: "take_snapshot",
      desc: "查看作业标题、状态(待批阅/未交/已完成)、截止日期",
    },
    how_get_workId: "从 onclick 属性提取 workId=NNN",
    next: "get_homework(取 workId)",
  };
}

function handleGetHomework(args) {
  const { courseId, classId, workId } = args;
  return {
    goal: "打开作业页，读取所有题目 / Open homework page and read questions",
    step1: { action: "navigate_page", url: urls.dowork(courseId, classId, workId) },
    step2: { action: "take_snapshot, read questions, options" },
    question_types: {
      "0": "单选 Single choice — click .answerBg[data=A/B/C/D]",
      "1": "多选 Multiple choice",
      "3": "判断 True/False — click correct option",
      "4": "简答 Essay — UE.getEditor('answer{id}').setContent(html)",
      "7": "计算题 Calculation — same as essay",
    },
    how_fill_mcq: "document.querySelectorAll('.answerBg[data=\"X\"]')[i].click()",
    how_fill_text: "UE.getEditor('answer{id}').setContent(html)",
    how_submit: "btnBlueSubmit(); setTimeout(submitCheckTimes, 1000);",
    next: "submit_homework(确定答案后)",
  };
}

function handleSubmitHomework(args) {
  const { courseId, classId, workId, answers } = args;
  const fillScripts = [];

  for (const [idx, answer] of Object.entries(answers)) {
    const a = String(answer).toUpperCase();
    if (["A", "B", "C", "D"].includes(a)) {
      fillScripts.push({
        question: Number(idx),
        type: "mcq",
        js: `document.querySelectorAll('.answerBg[data="${a}"]')[${idx}].click()`,
      });
    } else if (a === "TRUE" || a === "FALSE") {
      const offset = a === "TRUE" ? 0 : 1;
      fillScripts.push({
        question: Number(idx),
        type: "judge",
        js: `document.querySelectorAll('.answerBg')[${idx * 2 + offset}].click()`,
      });
    } else {
      fillScripts.push({
        question: Number(idx),
        type: "text",
        js: `UE.getEditor('answer${idx}').setContent('${String(answer).replace(/'/g, "\\'")}')`,
        note: "在 iframe 上下文中执行 / Execute in iframe context",
      });
    }
  }

  return {
    goal: `提交作业 workId=${workId}, ${Object.keys(answers).length} 题`,
    step1: { action: "navigate_page", url: urls.dowork(courseId, classId, workId) },
    step2: {
      action: "逐题执行 evaluate_script / Fill each question",
      scripts: fillScripts,
      note: "每题间隔 0.5-1s / Wait 0.5-1s between each",
    },
    step3: {
      action: "evaluate_script to submit",
      js: "btnBlueSubmit(); setTimeout(function(){ submitCheckTimes(); }, 1500);",
    },
    step4: {
      action: "等待后 take_snapshot / Wait then snapshot",
      note: "成功提示: 提交成功，等待教师批阅",
    },
    next: "get_homework_score(老师批改后)",
  };
}

function handleHomeworkscore(args) {
  const { courseId, classId, workId } = args;
  return {
    goal: "查看作业批阅结果 / View homework grading",
    step1: { action: "navigate_page", url: urls.viewWork(courseId, classId, workId) },
    note: "绿色对勾=正确, 红色叉=错误. 待批阅=not graded, 已完成=graded.",
  };
}

function handleAutoStudy(args) {
  const {
    courseId,
    classId,
    autoVideo = true,
    autoAudio = false,
    autoQuiz = true,
    autoSubmit = true,
    autoJump = false,
    answerInterval = 3.0,
    playbackRate = 2.0,
    minAccuracy = 0.6,
  } = args;

  return {
    studyUrl: urls.study(courseId, classId),
    settings: { autoVideo, autoAudio, autoQuiz, autoSubmit, autoJump, answerInterval, playbackRate, minAccuracy },
    task_point_types: {
      video: "/ananas/modules/video/index.html",
      audio: "/ananas/modules/audio/index.html",
      quiz: "/ananas/modules/work/index.html",
      pdf: "/ananas/modules/pdf/index.html",
    },
    workflow: [
      "1. navigate 到 studyUrl",
      "2. 等待 #iframe 加载 / Wait for #iframe to load",
      "3. 在 iframe 中找到所有 .ans-job-icon 元素",
      "4. 逐个处理:",
      "   - 跳过 .ans-job-finished 已完成项",
      "   - 读取 iframe src，匹配 task_point_types",
      "   - 视频: mute + speed + play, 轮询完成状态",
      "   - 音频: 同视频",
      "   - 测验: 解析 .TiMu, 搜索答案, 填入, 提交",
      "   - PDF: 滚动 #panView 到底部",
      "5. 如果 autoJump: 点击 .nextChapter 自动跳转",
    ].join("\n"),
    video_js: `const p=iframeWindow.videojs('video_html5_api');p.muted(true);p.playbackRate(${playbackRate});p.play();`,
    pdf_js: "const v=iframeWindow.document.querySelector('#panView').contentWindow;v.scrollTo(0,v.document.body.scrollHeight);",
  };
}

function handleDownloadMaterials(args) {
  const { courseId, classId } = args;
  return {
    goal: "下载课程资料 PPT/PDF/Word/Excel/视频 / Download materials",
    step1: { action: "navigate_page", url: urls.coursePage(courseId, classId) },
    step2: { action: "take_snapshot, click '资料' tab" },
    step3: { action: "take_snapshot, 查看可下载文件" },
    step4: { action: "点击链接下载 或 evaluate_script 提取所有 URL" },
  };
}

// ─── Server ───────────────────────────────────────────────────────────────

const server = new Server(
  { name: "easystudy-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  args ||= {};

  let result;
  try {
    if (name === "login") {
      result = await handleLogin(args);
    } else if (name === "auto_study") {
      result = handleAutoStudy(args);
    } else {
      // All other tools require login
      const err = checkLogin();
      if (err) { result = err; }
      else if (name === "get_courses") {
        result = handleGetCourses(args);
      } else if (name === "get_homeworks") {
        result = handleGetHomeworks(args);
      } else if (name === "get_homework") {
        result = handleGetHomework(args);
      } else if (name === "submit_homework") {
        result = handleSubmitHomework(args);
      } else if (name === "get_homework_score") {
        result = handleHomeworkscore(args);
      } else if (name === "download_materials") {
        result = handleDownloadMaterials(args);
      } else {
        result = { error: `Unknown tool: ${name}` };
      }
    }
  } catch (e) {
    result = { error: e.message };
  }

  return {
    content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
  };
});

// ─── Entry ────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Log to stderr so it doesn't corrupt stdio MCP transport
  process.stderr.write("easystudy-mcp v0.1.0 — 超星/学习通 MCP server ready\n");
}

main().catch((e) => {
  process.stderr.write(`Fatal: ${e.message}\n`);
  process.exit(1);
});
