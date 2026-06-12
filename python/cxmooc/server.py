"""
Chaoxing (学习通) MOOC MCP Server — 8 tools.

Architecture:
  login          → HTTP only (DES encrypt), standalone
  7 other tools  → return browser-operation plans for Chrome DevTools MCP
  Typical flow:  login → get_courses → get_homeworks → get_homework → submit_homework

Each non-login tool returns: url + step-by-step MCP tool calls + JS snippets.
The returned JSON is a "plan" that Claude reads and executes via Chrome DevTools MCP.
"""

import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .session import Session
from . import actions
from . import study as _study

_session = Session()
server = Server("cxmooc")


def _j(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def _check() -> dict | None:
    if not _session.logged_in:
        return {"error": "Please call login first / 请先调用 login 登录"}
    return None


# =============================================================================
# Tool definitions
# =============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="login",
            description=(
                "Login to Chaoxing with phone + password (DES encrypted). "
                "Must call this first before any other tool. "
                "Session cookie is stored automatically. "
                "Args: phone (string), password (string, plaintext). "
                "Returns: {success, message}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Registered phone number"},
                    "password": {"type": "string", "description": "Plaintext password"},
                },
                "required": ["phone", "password"],
            },
        ),
        Tool(
            name="get_courses",
            description=(
                "Get enrolled course list. Returns a URL + JS extract script. "
                "HOW TO USE: (1) navigate_page to the returned URL, "
                "(2) take_snapshot to see courses, OR evaluate_script with extract_js "
                "for structured JSON. Each course has: courseId, classId, name, url. "
                "NEXT: pass courseId+classId to get_homeworks."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_homeworks",
            description=(
                "Get homework list for a course. Returns browser operation steps. "
                "HOW TO USE: (1) navigate to course home, (2) click '作业' tab, "
                "(3) take_snapshot to see homework titles, statuses (待批阅/未交/已完成), "
                "and deadlines. Extract workId from onclick attributes. "
                "Args: courseId, classId (from get_courses). "
                "NEXT: pass workId to get_homework."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "courseId": {"type": "string", "description": "Course ID from get_courses"},
                    "classId": {"type": "string", "description": "Class ID from get_courses"},
                },
                "required": ["courseId", "classId"],
            },
        ),
        Tool(
            name="get_homework",
            description=(
                "Open a homework page and see all questions. "
                "HOW TO USE: (1) navigate_page to the returned URL, "
                "(2) take_snapshot to read questions, options (data=A/B/C/D), and types. "
                "Question types: 0=single-choice, 1=multi-choice, 3=true/false, 4=essay, 7=calc. "
                "For MCQs: click .answerBg[data='X'] to select. "
                "For text: UE.getEditor('answer{id}').setContent(html). "
                "Submit: btnBlueSubmit() then submitCheckTimes(). "
                "Args: courseId, classId, workId. "
                "NEXT: determine answers and call submit_homework."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "courseId": {"type": "string", "description": "Course ID"},
                    "classId": {"type": "string", "description": "Class ID"},
                    "workId": {"type": "string", "description": "Homework ID from get_homeworks"},
                },
                "required": ["courseId", "classId", "workId"],
            },
        ),
        Tool(
            name="submit_homework",
            description=(
                "Submit homework answers via browser automation. "
                "HOW TO USE: (1) navigate to homework page, "
                "(2) for each answer, evaluate_script to click MCQs or set editor content, "
                "(3) after all filled: btnBlueSubmit(); submitCheckTimes(). "
                "Answers format: {'question_index': 'answer_value'}. "
                "Example: {'0':'A', '1':'true', '2':'<p>solution text</p>'}. "
                "Question indices are 0-based. "
                "Args: courseId, classId, workId, answers (object). "
                "NEXT: call get_homework_score to check results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "courseId": {"type": "string", "description": "Course ID"},
                    "classId": {"type": "string", "description": "Class ID"},
                    "workId": {"type": "string", "description": "Homework ID"},
                    "token": {"type": "string", "description": "Optional page token"},
                    "enc": {"type": "string", "description": "Optional page enc param"},
                    "answers": {
                        "type": "object",
                        "description": (
                            "Answer map: {question_index: value}. "
                            "MCQ/TrueFalse: value is 'A'/'B'/'C'/'D' or 'true'/'false'. "
                            "Essay/Calc: value is HTML string."
                        ),
                    },
                },
                "required": ["courseId", "classId", "workId", "answers"],
            },
        ),
        Tool(
            name="get_homework_score",
            description=(
                "View homework grading results. "
                "HOW TO USE: (1) navigate_page to the returned URL, "
                "(2) take_snapshot to see correct answers, your answers, per-question scores, "
                "and total score. Green check = correct, red cross = wrong. "
                "Status '待批阅' = not yet graded; '已完成' = graded. "
                "Args: courseId, classId, workId."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "courseId": {"type": "string", "description": "Course ID"},
                    "classId": {"type": "string", "description": "Class ID"},
                    "workId": {"type": "string", "description": "Homework ID"},
                },
                "required": ["courseId", "classId", "workId"],
            },
        ),
        Tool(
            name="auto_study",
            description=(
                "Auto-complete course task points: videos, audio, chapter quizzes, PDFs. "
                "Returns browser automation plan with JS snippets. "
                "HOW IT WORKS: iterates .ans-job-icon elements in the study page iframe, "
                "skips finished ones (.ans-job-finished), handles each type: "
                "video → mute + speed up playback; audio → same; "
                "quiz → parse .TiMu, search answers, fill, submit; "
                "pdf → scroll #panView to bottom. "
                "Settings: autoVideo (default true), autoAudio (default false), "
                "autoQuiz (default true), autoSubmit (default true), "
                "autoJump (default false, be careful), playbackRate (default 2, max 4), "
                "answerInterval (default 3s), minAccuracy (default 0.6). "
                "WARNING: high playback rate may be detected. "
                "Args: courseId, classId."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "courseId": {"type": "string", "description": "Course ID"},
                    "classId": {"type": "string", "description": "Class ID"},
                    "autoVideo": {"type": "boolean", "description": "Auto-play videos (default true)"},
                    "autoAudio": {"type": "boolean", "description": "Auto-play audio (default false)"},
                    "autoQuiz": {"type": "boolean", "description": "Auto-solve quizzes (default true)"},
                    "autoSubmit": {"type": "boolean", "description": "Auto-submit quizzes (default true)"},
                    "autoJump": {"type": "boolean", "description": "Auto-advance chapters (default false, DANGER)"},
                    "answerInterval": {"type": "number", "description": "Seconds between answers (default 3)"},
                    "playbackRate": {"type": "number", "description": "Video speed multiplier (default 2, max 4)"},
                    "minAccuracy": {"type": "number", "description": "Min accuracy to auto-submit (default 0.6)"},
                },
                "required": ["courseId", "classId"],
            },
        ),
        Tool(
            name="download_materials",
            description=(
                "Download course materials (PPT/PDF/Word/Excel/video). "
                "HOW TO USE: (1) navigate to course home, (2) click '资料' tab, "
                "(3) take_snapshot to see downloadable files, "
                "(4) click download links or extract all URLs via evaluate_script. "
                "Args: courseId, classId."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "courseId": {"type": "string", "description": "Course ID"},
                    "classId": {"type": "string", "description": "Class ID"},
                },
                "required": ["courseId", "classId"],
            },
        ),
    ]


# =============================================================================
# Tool handlers
# =============================================================================

@server.call_tool()
async def call_tool(name: str, args: dict) -> list[TextContent]:
    # login and auto_study don't require prior login
    if name == "login":
        return _j(_session.login(args["phone"], args["password"]))
    if name == "auto_study":
        return _j(_study.auto_study(
            args["courseId"], args["classId"],
            auto_video=args.get("autoVideo", True),
            auto_audio=args.get("autoAudio", False),
            auto_quiz=args.get("autoQuiz", True),
            auto_submit=args.get("autoSubmit", True),
            auto_jump=args.get("autoJump", False),
            answer_interval=args.get("answerInterval", 3.0),
            playback_rate=args.get("playbackRate", 2.0),
            min_accuracy=args.get("minAccuracy", 0.6),
        ))

    # Remaining tools require login
    e = _check()
    if e:
        return _j(e)

    if name == "get_courses":
        return _j(actions.get_courses(_session))
    if name == "get_homeworks":
        return _j(actions.get_homeworks(_session, args["courseId"], args["classId"]))
    if name == "get_homework":
        return _j(actions.get_homework(_session, args["courseId"], args["classId"], args["workId"]))
    if name == "submit_homework":
        ans = {int(k): v for k, v in (args.get("answers") or {}).items()}
        return _j(actions.submit_homework(
            _session, args["courseId"], args["classId"], args["workId"],
            ans, args.get("token", ""), args.get("enc", ""),
        ))
    if name == "get_homework_score":
        return _j(actions.get_homework_score(_session, args["courseId"], args["classId"], args["workId"]))
    if name == "download_materials":
        return _j(actions.get_materials(_session, args["courseId"], args["classId"]))
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# =============================================================================
# Entry point
# =============================================================================

def main():
    import asyncio, os
    os.environ["PYTHONHTTPSVERIFY"] = "0"

    async def run():
        async with stdio_server() as (rs, ws):
            await server.run(rs, ws, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
