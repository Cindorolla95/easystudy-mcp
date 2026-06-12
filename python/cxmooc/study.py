"""
Auto-study for Chaoxing — browser-operated task-point completion.

Generates URL + settings + JS snippets for Chrome DevTools MCP.
"""


def auto_study(
    course_id: str,
    class_id: str,
    *,
    auto_video: bool = True,
    auto_audio: bool = False,
    auto_quiz: bool = True,
    auto_submit: bool = True,
    auto_jump: bool = False,
    answer_interval: float = 3.0,
    playback_rate: float = 2.0,
    min_accuracy: float = 0.6,
) -> dict:
    study_url = (
        "https://mooc1.chaoxing.com/mycourse/studentstudy"
        f"?courseId={course_id}&clazzid={class_id}&mooc2=1"
    )
    return {
        "studyUrl": study_url,
        "settings": {
            "autoVideo": auto_video,
            "autoAudio": auto_audio,
            "autoQuiz": auto_quiz,
            "autoSubmit": auto_submit,
            "autoJump": auto_jump,
            "answerInterval": answer_interval,
            "playbackRate": playback_rate,
            "minAccuracy": min_accuracy,
        },
        "task_point_types": {
            "video": "/ananas/modules/video/index.html",
            "audio": "/ananas/modules/audio/index.html",
            "quiz": "/ananas/modules/work/index.html",
            "pdf": "/ananas/modules/pdf/index.html",
        },
        "workflow": """
1. navigate to studyUrl
2. wait for #iframe to load
3. in the iframe, find all .ans-job-icon elements
4. for each:
   - skip if parent has .ans-job-finished class
   - read iframe src, match against task_point_types
   - video: mute + speed(PLAYBACK_RATE) + play, poll for completion
   - audio: same as video
   - quiz: parse .TiMu questions, search answers, fill, submit
   - pdf: scroll #panView to bottom
5. if autoJump: click .nextChapter, setInterval to detect and repeat
""".strip(),
        "video_js": (
            f"const p=iframeWindow.videojs('video_html5_api');"
            f"p.muted(true);p.playbackRate({playback_rate});p.play();"
            "setInterval(()=>{if(p.currentTime()>=p.duration()){/*done*/}},1000);"
        ),
        "pdf_js": (
            "const v=iframeWindow.document.querySelector('#panView').contentWindow;"
            "v.scrollTo(0,v.document.body.scrollHeight);"
        ),
    }
