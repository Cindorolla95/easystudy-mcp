"""
Chaoxing operations - browser operation plans.

Each tool returns a step-by-step plan: URLs, MCP tool calls, JS snippets.
The actual execution is done by Chrome DevTools MCP.
"""

import re
from typing import Any

from .session import Session


def _course_page(course_id: str, class_id: str) -> str:
    return (
        "https://mooc1-1.chaoxing.com/mooc-ans/visit/stucoursemiddle"
        f"?courseid={course_id}&clazzid={class_id}&vc=1&ismooc2=1"
    )


def _homework_list(course_id: str, class_id: str) -> str:
    return (
        "https://mooc1.chaoxing.com/mooc2/work/list"
        f"?courseId={course_id}&classId={class_id}"
    )


def _dowork(course_id: str, class_id: str, work_id: str) -> str:
    return (
        "https://mooc1.chaoxing.com/mooc2/work/dowork"
        f"?courseId={course_id}&classId={class_id}&workId={work_id}"
        "&answerId=&workRelationId=&enc="
    )


def _view_work(course_id: str, class_id: str, work_id: str) -> str:
    return (
        "https://mooc1.chaoxing.com/mooc2/work/view"
        f"?courseId={course_id}&classId={class_id}&workId={work_id}"
    )


def _materials(course_id: str, class_id: str) -> str:
    return (
        "https://mooc1.chaoxing.com/coursedata"
        f"?courseId={course_id}&classId={class_id}"
    )


def get_courses(session: Session) -> dict[str, Any]:
    url = "https://mooc1-1.chaoxing.com/visit/interaction?courseType=1&courseFolderId=0"
    return {
        "goal": "Get all enrolled courses",
        "step1": f"navigate_page to: {url}",
        "step2": "take_snapshot to see course names, teachers, courseid/clazzid",
        "step2_alt": "evaluate_script with extract_js for structured JSON output",
        "extract_js": (
            "()=>{var cs=[];"
            "document.querySelectorAll('a[href*=\"courseid=\"]').forEach(function(a){"
            "var m=a.href.match(/courseid=(\\d+).*?clazzid=(\\d+)/);"
            "if(m)cs.push({courseId:m[1],classId:m[2],name:a.textContent.trim()});"
            "});return cs;}"
        ),
        "output": "Each course: {courseId, classId, name}",
        "next": "get_homeworks with courseId and classId",
    }


def get_homeworks(session: Session, course_id: str, class_id: str) -> dict[str, Any]:
    return {
        "goal": "Get homework list for the course",
        "step1": {
            "action": "navigate_page",
            "url": _course_page(course_id, class_id),
            "desc": "Open course home page",
        },
        "step2": {
            "action": "click",
            "desc": "Click the '作业' (homework) tab in top navigation bar",
            "how": "take_snapshot first, then click the link element with text='作业'",
        },
        "step3": {
            "action": "take_snapshot",
            "desc": "View homework list loaded in iframe",
            "note": "Shows: title, status (待批阅/未交/已完成/待互评), deadline for each homework",
        },
        "how_get_workId": "Extract workId=NNN from onclick attribute of homework links",
        "next": "get_homework with workId",
    }


def get_homework(session: Session, course_id: str, class_id: str, work_id: str) -> dict[str, Any]:
    url = _dowork(course_id, class_id, work_id)
    return {
        "goal": "Open homework page and read all questions",
        "step1": {"action": "navigate_page", "url": url},
        "step2": {
            "action": "take_snapshot",
            "desc": "Read questions, options (data attributes), and types",
        },
        "question_types": {
            "0": "Single choice - click .answerBg[data=A/B/C/D] to select",
            "1": "Multiple choice",
            "3": "True/False - click correct option",
            "4": "Essay - use UE.getEditor('answer{id}').setContent(html)",
            "7": "Calculation - same as essay, fill with HTML",
        },
        "how_fill_mcq": {
            "js": "document.querySelectorAll('.answerBg[data=\"X\"]')[i].click()",
            "note": "X is A/B/C/D, i is question index (usually 0)",
        },
        "how_fill_text": {
            "js": "iframe.contentWindow.UE.getEditor('answer{id}').setContent(html)",
            "note": "Find the iframe containing the question first",
        },
        "how_submit": {
            "js": "btnBlueSubmit(); setTimeout(function(){ submitCheckTimes(); }, 1000);",
            "note": "btnBlueSubmit shows confirm dialog, submitCheckTimes confirms",
        },
        "next": "submit_homework after determining answers",
    }


def submit_homework(
    session: Session,
    course_id: str, class_id: str, work_id: str,
    answers: dict[int, str],
    token: str = "", enc: str = "",
) -> dict[str, Any]:
    url = _dowork(course_id, class_id, work_id)

    fill_scripts = []
    for idx, answer in answers.items():
        a = answer.upper() if isinstance(answer, str) else str(answer)
        if a in ("A", "B", "C", "D"):
            fill_scripts.append({
                "question": idx,
                "type": "mcq",
                "js": f"document.querySelectorAll('.answerBg[data=\"{a}\"]')[{idx}].click()",
            })
        elif a in ("TRUE", "FALSE"):
            offset = 0 if a == "TRUE" else 1
            fill_scripts.append({
                "question": idx,
                "type": "judge",
                "js": f"document.querySelectorAll('.answerBg')[{idx * 2 + offset}].click()",
            })
        else:
            fill_scripts.append({
                "question": idx,
                "type": "text",
                "js": f"UE.getEditor('answer{idx}').setContent('{answer}')",
                "note": "Execute this in the iframe context",
            })

    return {
        "goal": f"Submit homework workId={work_id}, {len(answers)} questions",
        "step1": {"action": "navigate_page", "url": url},
        "step2": {
            "action": "evaluate_script for each answer",
            "scripts": fill_scripts,
            "note": "Wait 0.5-1s between each script to mimic human behavior",
        },
        "step3": {
            "action": "evaluate_script to submit",
            "js": "btnBlueSubmit(); setTimeout(function(){ submitCheckTimes(); }, 1500);",
        },
        "step4": {
            "action": "wait then take_snapshot",
            "note": "Success message: 提交成功，等待教师批阅",
        },
        "next": "get_homework_score after teacher grades",
    }


def get_homework_score(session: Session, course_id: str, class_id: str, work_id: str) -> dict[str, Any]:
    return {
        "goal": "View homework grading results",
        "step1": {"action": "navigate_page", "url": _view_work(course_id, class_id, work_id)},
        "step2": {
            "action": "take_snapshot",
            "note": (
                "Shows: your answer, correct answer, score per question, total score. "
                "Green check = correct, red cross = wrong. "
                "Status 待批阅 = not yet graded; 已完成 = graded."
            ),
        },
    }


def get_materials(session: Session, course_id: str, class_id: str) -> dict[str, Any]:
    return {
        "goal": "Download course materials (PPT, PDF, Word, Excel, video)",
        "step1": {"action": "navigate_page", "url": _course_page(course_id, class_id)},
        "step2": {
            "action": "click",
            "desc": "Click '资料' (materials) tab in top nav",
            "how": "take_snapshot, find link with text='资料', click its uid",
        },
        "step3": {
            "action": "take_snapshot",
            "desc": "View downloadable files with names and links",
        },
        "step4": {
            "desc": "Download files",
            "how": "Click each link or extract all URLs with evaluate_script",
        },
    }
