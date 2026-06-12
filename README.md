# easystudy-mcp

> 让你更轻松的学习 — 超星/学习通 MCP 自动化服务器

[![npm](https://img.shields.io/npm/v/easystudy-mcp)](https://www.npmjs.com/package/easystudy-mcp)
[![license](https://img.shields.io/github/license/Cindorolla95/easystudy-mcp)](LICENSE)

**easystudy-mcp** 是一个连接**超星学习通**平台的 MCP (Model Context Protocol) 服务器，让你通过 AI 助手自动完成课程学习任务 — 查看课程、提交作业、自动刷课、下载资料，全部用自然语言交互。

8 个工具覆盖超星平台的日常操作，支持 Claude Code、Cowork、以及任何 MCP 兼容客户端。

---

## 工具列表

| 工具 | 功能 | 说明 |
|------|------|------|
| `login` | 登录超星 | 手机号 + 密码 (DES 加密) |
| `get_courses` | 获取课程列表 | 返回浏览器操作步骤 + JS 提取脚本 |
| `get_homeworks` | 获取作业列表 | 导航→点击作业标签→查看作业状态 |
| `get_homework` | 查看作业内容 | 读取题目、选项、题目类型 |
| `submit_homework` | 提交作业答案 | 自动填入 MCQs / 简答题，一键提交 |
| `get_homework_score` | 查看批阅结果 | 显示得分、正确答案对比 |
| `auto_study` | 自动完成任务点 | 视频/音频/测验/PDF 全自动处理 |
| `download_materials` | 下载课程资料 | PPT/PDF/Word/Excel/视频 |

---

## 安装方式

### 方式一：npx (推荐，零安装)

在 Claude Code、Cowork 或其他 MCP 客户端中直接配置：

```json
{
  "mcpServers": {
    "easystudy": {
      "command": "npx",
      "args": ["easystudy-mcp"]
    }
  }
}
```

npx 会在首次运行时自动下载并缓存，之后直接从缓存启动。

### 方式二：全局安装

```bash
npm install -g easystudy-mcp
```

安装后在 MCP 客户端中配置：

```json
{
  "mcpServers": {
    "easystudy": {
      "command": "easystudy-mcp"
    }
  }
}
```

### 方式三：本地安装

```bash
git clone https://github.com/Cindorolla95/easystudy-mcp.git
cd easystudy-mcp
npm install
```

```json
{
  "mcpServers": {
    "easystudy": {
      "command": "node",
      "args": ["/path/to/easystudy-mcp/src/index.js"]
    }
  }
}
```

---

## Claude Code 配置

编辑 `.claude.json` 或项目根目录的 `CLAUDE.md`：

```json
{
  "mcpServers": {
    "easystudy": {
      "command": "npx",
      "args": ["easystudy-mcp"]
    }
  }
}
```

启动 Claude Code 后 MCP 工具自动加载，然后就可以用自然语言操作超星了：

> "登录超星账号" → "看看我有哪些课程" → "统计学有什么作业" → "帮我做第一份作业"

---

## Cowork 配置

在 Cowork 的 MCP 设置中添加：

```
npx easystudy-mcp
```

---

## 使用流程

### 典型作业流程

```
1. login(phone, password)           → 登录超星
2. get_courses()                     → 获取课程列表，拿到 courseId 和 classId
3. get_homeworks(courseId, classId)  → 获取作业列表，拿到 workId
4. get_homework(courseId, classId, workId) → 查看题目 (题目类型、选项)
5. submit_homework(courseId, classId, workId, answers) → 提交答案
6. get_homework_score(courseId, classId, workId) → 查看批改结果
```

### 自动刷课流程

```
1. login(phone, password)  → 登录
2. auto_study(courseId, classId, {
     autoVideo: true,   // 自动播放视频（静音+加速）
     autoQuiz: true,    // 自动完成章节测验
     playbackRate: 2,   // 视频倍速 (最高 4x)
   })
```

### 答案格式

```json
// 单选/多选 — 选项字母
{"0": "A", "1": "C", "2": "D"}

// 判断题 — true/false
{"0": "true", "1": "false"}

// 简答题/计算题 — HTML 文本
{"3": "<p>答：假设检验的步骤如下...</p>"}

// 混合使用
{
  "0": "A",           // 单选题第 1 题，选 A
  "1": "false",       // 判断题第 2 题，选错
  "2": "<p>解：μ=100, σ=15</p>"  // 计算题
}
```

---

## 工作原理

**easystudy-mcp** 采用的是 **浏览器操作计划** 架构：

- `login` 工具使用 HTTP + DES 加密直接完成登录
- 其他 7 个工具返回**结构化的操作计划**（URL、步骤、JS 代码片段），由 AI 代理通过 Chrome DevTools MCP 在浏览器中实际执行

这样设计的原因是超星页面是 JS 动态渲染的，纯 HTTP 请求无法获取课程列表、作业内容等数据。返回"操作计划"的方式让 AI 能够理解每一步做什么，并在浏览器中灵活执行。

---

## 安全性

- 密码通过 DES 加密传输（与超星 Android App 加密方式一致）
- 会话 cookie 仅保存在 MCP 进程内存中
- 不会上传任何数据到第三方服务器
- 自动刷课时视频已静音 + 倍速播放，避免干扰正常使用

---

## 从源码运行

```bash
git clone https://github.com/Cindorolla95/easystudy-mcp.git
cd easystudy-mcp
npm install
node src/index.js
```

MCP 协议通过 stdio 通信，服务启动后等待 MCP 客户端连接。

---

## Python 版本

项目同时提供 Python 版本的超星 MCP 服务器 (`python/` 目录)。适用于偏好 Python 环境的用户。

```bash
cd python/cxmooc_mcp
pip install -e . --break-system-packages
cxmooc-mcp  # 启动 MCP 服务
```

Python 版本的 MCP 客户端配置：

```json
{
  "mcpServers": {
    "easystudy": {
      "command": "python",
      "args": ["-m", "cxmooc"]
    }
  }
}
```

---

## License

Apache-2.0

---

<p align="center">
  <sub>让 AI 帮你搞定超星学习通 ✨</sub>
</p>
