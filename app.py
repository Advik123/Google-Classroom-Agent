import base64
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta
from functools import wraps

import google.generativeai as genai
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    stream_with_context,
    url_for,
)
from flask_cors import CORS
from google.api_core.exceptions import ResourceExhausted

import config
from doc_reader import get_homework_entries

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="public/static",
    static_url_path="/static",
)
CORS(app)


def _resolve_secret_key() -> str:
    """
    Flask requires a non-empty secret_key to sign sessions. On Vercel, if
    SECRET_KEY is missing but APP_PASSWORD is set, derive a stable key from
    APP_PASSWORD so login does not 500. Prefer setting SECRET_KEY in production
    so you can rotate the password without invalidating all sessions.
    """
    explicit = os.getenv("SECRET_KEY", "").strip()
    if explicit:
        return explicit
    app_password = os.getenv("APP_PASSWORD", "").strip()
    if app_password:
        return hashlib.sha256(
            b"GoogleClassroomAgent.session.v1:" + app_password.encode("utf-8")
        ).hexdigest()
    return "dev-insecure-set-SECRET_KEY-or-APP_PASSWORD"


app.secret_key = _resolve_secret_key()
app.permanent_session_lifetime = timedelta(days=31)


def login_required(f):
    @wraps(f)
    def _wrapped(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return _wrapped

MODEL_CHAIN = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemma-4-31b-it",
]

SYSTEM_PROMPT = (
    "You are a helpful homework tutor. Explain reasoning clearly and encourage "
    "understanding over just giving answers. When the user provides subject "
    "context, a primary assignment, and a list of other work in the same "
    "subject, focus your help on the primary assignment unless the student "
    "clearly asks about another item."
)

STUDY_SYSTEM_PROMPT = (
    "You are a study tool. Generate educational flashcards and quiz questions "
    "based on the provided content or topic. Return ONLY valid JSON with no "
    "markdown, no backticks, no preamble. Every quiz item must include an "
    "'explanation' string (2-3 sentences, plain prose) for the correct answer."
)

SUBJECT_COLORS = {
    "ELA": "#FF6B6B",
    "Spanish": "#FFB347",
    "Science": "#4ECDC4",
    "SS": "#45B7D1",
    "Geometry": "#A78BFA",
}


def _resolve_doc_id():
    candidate_names = (
        "HOMEWORK_LOG_DOC_ID",
        "HOMEWORK_DOC_ID",
        "GOOGLE_DOC_ID",
        "DOC_ID",
        "HOMEWORK_LOG_DOC",
    )
    for name in candidate_names:
        value = getattr(config, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    env_value = os.getenv("HOMEWORK_LOG_DOC_ID", "").strip()
    if env_value:
        return env_value

    raise RuntimeError(
        "No homework doc ID found in config.py or HOMEWORK_LOG_DOC_ID environment variable."
    )


def _format_month_day(input_date: date) -> str:
    return input_date.strftime("%b %d").replace(" 0", " ")


def _get_due_label(due: date, today: date) -> str:
    if due < today:
        return "Overdue"
    if due == today:
        return "Today"
    if due == today + timedelta(days=1):
        return "Tomorrow"
    if due <= today + timedelta(days=7):
        return f"This {due.strftime('%A')}"
    return _format_month_day(due)


def _sort_key(item):
    """
    Sort by class (subject) A→Z, then by due urgency within class:
    overdue first (most recently due first = closest to today), then today/future
    (soonest first).
    """
    subject = (item.get("subject") or "").strip().lower()
    due_date = item.get("_due_date_obj")
    today = date.today()
    if not due_date:
        return (subject, 2, 0)
    if due_date < today:
        return (subject, 0, -due_date.toordinal())
    return (subject, 1, due_date.toordinal())


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        app_password = os.getenv("APP_PASSWORD", "")
        if app_password and request.form.get("password") == app_password:
            session["authed"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "Incorrect password."
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("index.html")


@app.get("/help")
@login_required
def help_page():
    return render_template("help.html")


@app.get("/api/homework")
@login_required
def api_homework():
    doc_id = _resolve_doc_id()
    raw_entries = get_homework_entries(doc_id)
    today = date.today()

    enriched = []
    for entry in raw_entries:
        due_str = entry.get("due_date", "")
        due_obj = None
        if due_str:
            try:
                due_obj = date.fromisoformat(due_str)
            except ValueError:
                due_obj = None

        subject = entry.get("subject", "").strip()
        enriched.append(
            {
                "due_date": due_obj.isoformat() if due_obj else due_str,
                "due_label": _get_due_label(due_obj, today)
                if due_obj
                else "Unknown",
                "subject": subject,
                "subject_color": SUBJECT_COLORS.get(subject, "#8B8B93"),
                "description": entry.get("description", "").strip(),
                "completed": bool(entry.get("completed", False)),
                "_due_date_obj": due_obj,
            }
        )

    enriched.sort(key=_sort_key)

    entries = []
    for item in enriched:
        item.pop("_due_date_obj", None)
        entries.append(item)

    return jsonify(
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "entries": entries,
        }
    )


def _resolve_chat_api_key() -> str:
    """Use the same key source as the rest of the project: env vars then config."""
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    configured = getattr(config, "GEMINI_API_KEY", None)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return ""


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        isinstance(exc, ResourceExhausted)
        or "429" in message
        or "quota" in message
        or "rate" in message
    )


def _normalize_role(role: str) -> str:
    if role in {"assistant", "model"}:
        return "model"
    return "user"


def _build_gemini_contents(messages, attachments):
    contents = []
    last_user_index = -1

    for message in messages:
        role = _normalize_role(str(message.get("role", "user")))
        text = str(message.get("content", "")).strip()
        if not text:
            continue
        if role == "user":
            last_user_index = len(contents)
        contents.append({"role": role, "parts": [{"text": text}]})

    if attachments and last_user_index >= 0:
        inline_parts = []
        for attachment in attachments:
            media_type = str(attachment.get("media_type", "")).strip()
            data = str(attachment.get("data", "")).strip()
            if not media_type or not data:
                continue
            inline_parts.append({"inline_data": {"mime_type": media_type, "data": data}})
        if inline_parts:
            existing_text_parts = [
                part
                for part in contents[last_user_index]["parts"]
                if isinstance(part, dict) and part.get("text")
            ]
            contents[last_user_index]["parts"] = inline_parts + existing_text_parts

    return contents


def _chunk_text(chunk) -> str:
    if chunk is None:
        return ""
    try:
        text = getattr(chunk, "text", "")
        if text:
            return text
    except Exception:
        pass

    parts = []
    candidates = getattr(chunk, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            value = getattr(part, "text", "")
            if value:
                parts.append(value)
    return "".join(parts)


def _format_sse_data(text: str) -> str:
    lines = str(text).splitlines() or [""]
    return "".join(f"data: {line}\n" for line in lines) + "\n"


def _start_stream_with_fallback(contents):
    for model_name in MODEL_CHAIN:
        try:
            model = genai.GenerativeModel(
                model_name=model_name, system_instruction=SYSTEM_PROMPT
            )
            stream = model.generate_content(contents, stream=True)
            iterator = iter(stream)
            first_chunk = next(iterator, None)
            return model_name, first_chunk, iterator
        except Exception as exc:
            if _is_rate_limit_error(exc):
                app.logger.warning("Rate limited on model %s", model_name)
                continue
            raise
    return None, None, None


def _build_study_prompt(source_text: str) -> str:
    return (
        "Generate study material from the following: "
        f"{source_text}. Return a JSON object with two keys: 'flashcards' "
        "(array of {front, back} objects) and 'quiz' (array of {question, "
        "type, options, answer, explanation} objects where type is "
        "'multiple_choice' or 'true_false', options is an array of 4 strings "
        "for multiple_choice or ['True','False'] for true_false, answer is the "
        "correct option string, and explanation is a string of exactly 2-3 "
        "sentences of plain prose (no markdown, no lists) that explains why "
        "answer is correct and briefly why the other options are wrong when "
        "that applies). Generate as many cards and questions as the content "
        "supports - aim for at least 10 flashcards and 8 quiz questions when "
        "the topic allows. For flashcards, front = term/concept, back = "
        "definition/explanation. For quiz questions, write clear unambiguous "
        "questions."
    )


def _extract_response_text(response) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text

    collected = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            value = str(getattr(part, "text", "") or "")
            if value:
                collected.append(value)
    return "".join(collected).strip()


def _parse_study_json(raw_text: str):
    candidate = str(raw_text or "").strip()
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _coerce_study_output(parsed_payload: dict, mode: str) -> dict:
    flashcards = parsed_payload.get("flashcards")
    quiz = parsed_payload.get("quiz")
    if not isinstance(flashcards, list):
        flashcards = []
    if not isinstance(quiz, list):
        quiz = []

    cleaned_flashcards = []
    for item in flashcards:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front", "")).strip()
        back = str(item.get("back", "")).strip()
        if not front or not back:
            continue
        cleaned_flashcards.append({"front": front, "back": back})

    cleaned_quiz = []
    for item in quiz:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        q_type = str(item.get("type", "")).strip()
        options = item.get("options")
        answer = str(item.get("answer", "")).strip()
        if q_type not in {"multiple_choice", "true_false"} or not question or not answer:
            continue
        if not isinstance(options, list):
            continue
        normalized_options = [str(opt).strip() for opt in options if str(opt).strip()]
        if q_type == "multiple_choice" and len(normalized_options) != 4:
            continue
        if q_type == "true_false":
            normalized_options = ["True", "False"]
            lowered = answer.lower()
            if lowered in {"true", "false"}:
                answer = "True" if lowered == "true" else "False"
            if answer not in {"True", "False"}:
                continue
        if answer not in normalized_options:
            continue
        explanation = str(item.get("explanation", "")).strip()
        cleaned_quiz.append(
            {
                "question": question,
                "type": q_type,
                "options": normalized_options,
                "answer": answer,
                "explanation": explanation,
            }
        )

    if mode == "flashcards":
        cleaned_quiz = []
    elif mode == "quiz":
        cleaned_flashcards = []

    return {"flashcards": cleaned_flashcards, "quiz": cleaned_quiz}


def _study_data_path() -> str:
    return os.path.join(app.root_path, "study_data.json")


def _load_study_data() -> dict:
    path = _study_data_path()
    if not os.path.exists(path):
        return {"sessions": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {"sessions": []}
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        sessions = []
    return {"sessions": sessions}


def _save_study_data(payload: dict) -> None:
    path = _study_data_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


@app.post("/api/chat")
@login_required
def api_chat():
    api_key = _resolve_chat_api_key()
    if not api_key:
        return jsonify(
            {
                "error": (
                    "Missing Gemini API key: set GOOGLE_API_KEY or GEMINI_API_KEY "
                    "in the environment, or GEMINI_API_KEY in config.py"
                )
            }
        ), 500
    genai.configure(api_key=api_key)

    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages") or []
    attachments = payload.get("attachments") or []
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "messages must be a non-empty array"}), 400
    if not isinstance(attachments, list):
        return jsonify({"error": "attachments must be an array"}), 400

    contents = _build_gemini_contents(messages, attachments)
    if not contents:
        return jsonify({"error": "No valid messages provided"}), 400

    try:
        model_name, first_chunk, iterator = _start_stream_with_fallback(contents)
    except Exception as exc:
        app.logger.exception("Gemini request failed")
        return jsonify({"error": str(exc)}), 500

    if not model_name:
        return jsonify({"error": "All models rate limited, try again later"}), 503

    @stream_with_context
    def event_stream():
        try:
            first_text = _chunk_text(first_chunk)
            if first_text:
                yield _format_sse_data(first_text)
            for chunk in iterator:
                chunk_text = _chunk_text(chunk)
                if chunk_text:
                    yield _format_sse_data(chunk_text)
        except Exception:
            app.logger.exception("Stream interrupted for model %s", model_name)
        finally:
            yield "data: [DONE]\n\n"

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["X-Model-Used"] = model_name
    return response


@app.get("/study")
@login_required
def study_page():
    return render_template("study.html")


@app.get("/study-assets/<path:filename>")
@login_required
def study_asset(filename):
    return send_from_directory("static", filename)


@app.post("/api/generate-study")
@login_required
def api_generate_study():
    mode = ""
    prompt_text = ""
    attachment = None
    source_for_prompt = ""

    if request.content_type and "multipart/form-data" in request.content_type:
        mode = str(request.form.get("mode", "both")).strip().lower()
        uploaded_file = request.files.get("file")
        if not uploaded_file:
            return jsonify({"error": "Missing file upload"}), 400
        file_bytes = uploaded_file.read()
        if not file_bytes:
            return jsonify({"error": "Uploaded file is empty"}), 400
        mime_type = str(uploaded_file.mimetype or "").strip() or "application/octet-stream"
        attachment = {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(file_bytes).decode("utf-8"),
            }
        }
        source_for_prompt = uploaded_file.filename or "uploaded file"
    else:
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode", "both")).strip().lower()
        prompt_text = str(payload.get("prompt", "")).strip()
        if not prompt_text:
            return jsonify({"error": "prompt is required"}), 400
        source_for_prompt = prompt_text

    if mode not in {"flashcards", "quiz", "both"}:
        return jsonify({"error": "mode must be flashcards, quiz, or both"}), 400

    api_key = _resolve_chat_api_key()
    if not api_key:
        return jsonify(
            {
                "error": (
                    "Missing Gemini API key: set GOOGLE_API_KEY or GEMINI_API_KEY "
                    "in the environment, or GEMINI_API_KEY in config.py"
                )
            }
        ), 500
    genai.configure(api_key=api_key)

    user_prompt = _build_study_prompt(source_for_prompt)
    parts = []
    if attachment:
        parts.append(attachment)
    parts.append({"text": user_prompt})
    contents = [{"role": "user", "parts": parts}]

    last_exc = None
    raw_response_text = ""
    for model_name in MODEL_CHAIN:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=STUDY_SYSTEM_PROMPT,
            )
            response = model.generate_content(contents)
            raw_response_text = _extract_response_text(response)
            break
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc):
                app.logger.warning("Rate limited on model %s", model_name)
                continue
            app.logger.exception("Study generation failed on %s", model_name)
            return jsonify({"error": str(exc)}), 500
    else:
        if last_exc:
            app.logger.exception("Study generation failed")
            return jsonify({"error": str(last_exc)}), 500
        return jsonify({"error": "All models rate limited, try again later"}), 503

    parsed = _parse_study_json(raw_response_text)
    if not isinstance(parsed, dict):
        return jsonify({"error": "Could not parse study content"}), 422

    return jsonify(_coerce_study_output(parsed, mode))


@app.post("/api/save-progress")
@login_required
def api_save_progress():
    payload = request.get_json(silent=True) or {}
    wrong_items = payload.get("wrong_items", [])
    session_entry = {
        "session_id": str(payload.get("session_id", "")).strip(),
        "type": str(payload.get("type", "")).strip(),
        "source": str(payload.get("source", "")).strip(),
        "date": str(payload.get("date", "")).strip(),
        "score": int(payload.get("score", 0) or 0),
        "total": int(payload.get("total", 0) or 0),
        "wrong_items": wrong_items if isinstance(wrong_items, list) else [],
    }
    if session_entry["type"] not in {"flashcards", "quiz"}:
        return jsonify({"error": "type must be flashcards or quiz"}), 400
    if not session_entry["session_id"] or not session_entry["source"] or not session_entry["date"]:
        return jsonify({"error": "session_id, source, and date are required"}), 400

    data = _load_study_data()
    sessions = data.get("sessions", [])
    sessions.append(session_entry)
    data["sessions"] = sessions[-100:]
    _save_study_data(data)
    return jsonify({"ok": True})


@app.get("/api/get-progress")
@login_required
def api_get_progress():
    return jsonify(_load_study_data())


if __name__ == "__main__":
    app.run(debug=True)
