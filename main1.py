import streamlit as st
import google.generativeai as genai
from urllib.parse import quote_plus
from fpdf import FPDF
import textwrap
import hashlib
import json
import os
from datetime import datetime

# =========================
# CONFIG
# =========================

st.set_page_config(
    page_title="Smart Course Builder Using GEN AI",
    page_icon="📚",
    layout="wide",
)

VISIBLE_MODEL_NAME = "Gemini 2.0"
GEMINI_MODEL = "gemini-2.5-flash"

# ---- READ API KEY FROM SECRETS (HIDDEN) ----
# Put GEMINI_API_KEY in .streamlit/secrets.toml (local)
# or in Streamlit Cloud -> Settings -> Secrets
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)

DATA_FILE = "users_data.json"
MAX_COURSES_PER_USER = 20

try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        client = genai.GenerativeModel(GEMINI_MODEL)
    else:
        client = None
except Exception:
    client = None


# =========================
# PERSISTENT USER & COURSE STORAGE
# =========================

def _hash(p: str) -> str:
    return hashlib.sha256(p.encode("utf-8")).hexdigest()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
# users_data structure:
# {
#   "username": {
#       "name": "...",
#       "password_hash": "...",
#       "courses": [
#           {
#               "id": "timestamp",
#               "title": "...",
#               "category": "...",
#               "created_at": "...",
#               "full_text": "...."
#           },
#           ...
#       ]
#   },
#   ...
# }

users_data = load_data()  # [file:1]

# =========================
# SESSION STATE
# =========================

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

if "screen" not in st.session_state:
    st.session_state.screen = "auth"  # "auth" or "builder"

if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = 0

if "wizard_data" not in st.session_state:
    st.session_state.wizard_data = {
        "category": "Programming",
        "topic": "",
        "extra_details": "",
        "difficulty": "Beginner",
        "duration": "1 Hour Quick Start",
        "include_video": "Yes",
        "modules": 5,
        "style": "Practical",
        "notes": "Explain everything in depth with long, detailed paragraphs.",
    }

if "course_full" not in st.session_state:
    st.session_state.course_full = ""

if "modules" not in st.session_state:
    st.session_state.modules = []

if "current_course_id" not in st.session_state:
    st.session_state.current_course_id = None

# =========================
# HELPERS
# =========================

def get_current_user():
    return st.session_state.logged_in_user

def require_login():
    if not get_current_user():
        st.warning("Please login to continue.")
        st.session_state.screen = "auth"
        st.stop()

def call_gemini(prompt: str) -> str:
    if not client:
        return "⚠️ Gemini client is not configured. Check API key."
    try:
        resp = client.generate_content(prompt)
        return resp.text
    except Exception as e:
        return f"⚠️ Error while calling Gemini: {e}"

def youtube_search_link(course_title: str, module_title: str) -> str:
    query_text = f"{course_title} {module_title} tutorial"
    q = quote_plus(query_text)
    return f"https://www.youtube.com/results?search_query={q}"

def wrap_text(text, width=90):
    return "\n".join(textwrap.TextWrapper(width=width).wrap(text))

def strip_unsupported_chars(text: str) -> str:
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return text.encode("latin-1", "ignore").decode("latin-1")

class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Smart Course Builder Using GEN AI - Course Material", ln=True, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def chapter_title(self, label):
        label = strip_unsupported_chars(label)
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, label, ln=True)
        self.ln(4)

    def chapter_body(self, body):
        body = strip_unsupported_chars(body)
        self.set_font("Arial", "", 11)
        wrapped = wrap_text(body, width=90)
        self.multi_cell(0, 5, wrapped)
        self.ln()

def create_pdf(title: str, full_text: str) -> bytes:
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.chapter_title(title)
    pdf.chapter_body(full_text)
    pdf_bytes = pdf.output(dest="S").encode("latin-1")
    return pdf_bytes
     

def parse_modules(text: str):
    lines = text.splitlines()
    modules = []
    current_title = None
    current_body = []

    def is_module_line(line: str) -> bool:
        s = line.strip()
        return s.lower().startswith("module ") and ":" in s

    def push():
        nonlocal current_title, current_body
        if current_title is not None:
            body_text = "\n".join(current_body).strip()
            modules.append({"title": current_title.strip(), "description": body_text})

    for ln in lines:
        if is_module_line(ln):
            push()
            current_title = ln.strip()
            current_body = []
        else:
            if current_title is None:
                current_title = "Module 1: Introduction"
            current_body.append(ln)

    push()
    return modules

def get_user_courses(username: str):
    user = users_data.get(username, {})
    return user.get("courses", [])

def set_user_courses(username: str, courses):
    if username not in users_data:
        return
    users_data[username]["courses"] = courses
    save_data(users_data)

# =========================
# AUTH SCREEN
# =========================

def auth_screen():
    st.title("🔐 Smart Course Builder Using GEN AI Login")

    if get_current_user():
        st.success(f"Already logged in as {get_current_user()['username']}")
        if st.button("Go to Course Builder"):
            st.session_state.screen = "builder"
            st.rerun()
        return

    tab_login, tab_signup = st.tabs(["Login", "Create Account"])

    with tab_login:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")

        if st.button("Login"):
            user = users_data.get(u)
            if not user:
                st.error("User not found. Please create an account.")
            elif _hash(p) != user["password_hash"]:
                st.error("Invalid password.")
            else:
                st.session_state.logged_in_user = {"username": u, "name": user.get("name", u)}
                st.success("Login successful!")
                st.session_state.screen = "builder"
                st.rerun()

    with tab_signup:
        nu = st.text_input("New username", key="su_u")
        nm = st.text_input("Full name", key="su_n")
        npw = st.text_input("Password", type="password", key="su_p")
        cpw = st.text_input("Confirm password", type="password", key="su_cp")

        if st.button("Create Account"):
            if not nu or not npw:
                st.error("Username and password required.")
            elif nu in users_data:
                st.error("Username already exists.")
            elif npw != cpw:
                st.error("Passwords do not match.")
            else:
                users_data[nu] = {
                    "name": nm or nu,
                    "password_hash": _hash(npw),
                    "courses": [],
                }
                save_data(users_data)
                st.success("Account created. You can login now.")

# =========================
# BUILDER SCREEN
# =========================

def builder_screen():
    require_login()
    user = get_current_user()
    username = user["username"]

    # Header
    st.markdown("### ⚡ Smart Course Builder Using GEN AI")
    col_user, col_model = st.columns([2, 2])

    with col_user:
        st.write(f"Logged in as **{username}**")
        if st.button("Logout"):
            st.session_state.logged_in_user = None
            st.session_state.screen = "auth"
            st.rerun()

    with col_model:
        st.caption(f"Powered by {VISIBLE_MODEL_NAME}")

    # Per-user course list
    st.markdown("#### 📁 Your Courses")
    courses = get_user_courses(username)

    if courses:
        for c in courses:
            col1, col2, col3 = st.columns([4, 2, 1])
            with col1:
                st.write(f"**{c['title']}** \n_{c['category']}_ · {c['created_at']}")
            with col2:
                if st.button("Load course", key=f"load_{c['id']}"):
                    st.session_state.course_full = c["full_text"]
                    st.session_state.modules = parse_modules(c["full_text"])
                    st.session_state.current_course_id = c["id"]
                    st.session_state.wizard_step = 4
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"del_{c['id']}"):
                    new_courses = [x for x in courses if x["id"] != c["id"]]
                    set_user_courses(username, new_courses)
                    st.success("Course deleted.")
                    st.rerun()
    else:
        st.info("No courses yet. Create your first course below.")

    st.markdown("---")

    step = st.session_state.wizard_step
    d = st.session_state.wizard_data

    # STEP 0
    if step == 0:
        st.subheader("Step 1: Basic Info")

        d["category"] = st.selectbox(
            "Course Category",
            [
                "Programming",
                "Science",
                "Mathematics",
                "Business",
                "Design",
                "Marketing",
                "Languages",
                "Health",
                "Other",
            ],
            index=0,
        )

        d["topic"] = st.text_input(
            "Main Topic / Course Title",
            value=d.get("topic", ""),
            placeholder="e.g., Mastering Canva for Beginners",
        )

        d["extra_details"] = st.text_area(
            "Extra details about topic (optional)",
            value=d.get("extra_details", ""),
            placeholder="What exactly should this course cover?",
            height=80,
        )

        d["modules"] = st.number_input(
            "Number of modules",
            min_value=1,
            max_value=20,
            step=1,
            value=int(d.get("modules", 5)),
        )

        c1, c2 = st.columns(2)
        with c1:
            st.button("⬅ Prev", disabled=True)
        with c2:
            if st.button("Next ➜", key="s0_next"):
                st.session_state.wizard_step = 1
                st.rerun()

    # STEP 1
    elif step == 1:
        st.subheader("Step 2: Learner Profile")

        c1, c2 = st.columns(2)
        with c1:
            d["difficulty"] = st.selectbox(
                "Difficulty Level",
                ["Beginner", "Intermediate", "Advanced"],
                index=["Beginner", "Intermediate", "Advanced"].index(
                    d.get("difficulty", "Beginner")
                ),
            )

        with c2:
            d["duration"] = st.selectbox(
                "Course Duration",
                [
                    "30 Minutes Crash Course",
                    "1 Hour Quick Start",
                    "3 Hours Intensive",
                    "1 Day Workshop",
                    "1 Week Bootcamp",
                ],
                index=1,
            )

        d["target_audience"] = st.text_area(
            "Target Audience",
            value=d.get("target_audience", "Anyone interested in the topic."),
            height=80,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("⬅ Prev", key="s1_prev"):
                st.session_state.wizard_step = 0
                st.rerun()
        with c2:
            if st.button("Next ➜", key="s1_next"):
                st.session_state.wizard_step = 2
                st.rerun()

    # STEP 2
    elif step == 2:
        st.subheader("Step 3: Options")

        d["style"] = st.selectbox(
            "Teaching Style",
            ["Practical", "Exam-Oriented", "Story Based", "Corporate Training"],
            index=0,
        )

        d["notes"] = st.text_area(
            "Special Instructions for AI",
            value=d.get(
                "notes", "Explain everything in depth with long, detailed paragraphs."
            ),
            height=120,
        )

        d["include_video"] = st.radio(
            "Include YouTube links after each module?",
            ["Yes", "No"],
            index=0 if d.get("include_video", "Yes") == "Yes" else 1,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("⬅ Prev", key="s2_prev"):
                st.session_state.wizard_step = 1
                st.rerun()
        with c2:
            if st.button("Next ➜", key="s2_next"):
                st.session_state.wizard_step = 3
                st.rerun()

    # STEP 3
    elif step == 3:
        st.subheader("Step 4: Generate Course")

        user_courses = get_user_courses(username)
        if len(user_courses) >= MAX_COURSES_PER_USER:
            st.error(
                f"You already have {MAX_COURSES_PER_USER} courses. Delete one to create a new course."
            )
        else:
            if st.button("Generate Course with Gemini ⚡"):
                prompt = f"""
You are an expert course designer.

Create a LONG, DETAILED course as plain text with the following structure:

1. Overall course title and a very detailed introduction in paragraph form (at least 3 long paragraphs).

2. A section "Learning Objectives" written mainly as paragraphs. A few bullet points are allowed.

3. EXACTLY {int(d['modules'])} main modules.

VERY IMPORTANT MODULE FORMAT:

- Each module MUST start on a new line with a title like:
  Module X: Meaningful Title
  where X is the module number (1, 2, 3, ...).

- That line must start with 'Module ' and contain a colon ':'.

For EACH module:
- After the 'Module X: ...' line, write rich, long explanations in multiple paragraphs, going deep into the topic.
- Use bullet points ONLY when really needed for lists or key highlights.

After all modules:
- Add a final section "Summary / Revision Notes" in long paragraphs.
- Do NOT add any quizzes or question-answer sections.
- Do NOT include any links or URLs.

Course details:
- Course Title: {d['topic']}
- Category: {d['category']}
- Target Audience: {d['target_audience']}
- Difficulty: {d['difficulty']}
- Duration: {d['duration']}
- Teaching Style: {d['style']}

Extra details about the topic:
{d['extra_details']}

Special instructions from creator:
{d['notes']}
"""
                with st.spinner("Generating course with Gemini..."):
                    full_text = call_gemini(prompt)
                    st.session_state.course_full = full_text
                    st.session_state.modules = parse_modules(full_text)

                    new_course = {
                        "id": datetime.utcnow().strftime("%Y%m%d%H%M%S%f"),
                        "title": d["topic"] or "Generated Course",
                        "category": d["category"],
                        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                        "full_text": full_text,
                    }

                    user_courses.append(new_course)
                    set_user_courses(username, user_courses)
                    st.session_state.current_course_id = new_course["id"]
                    st.success("Course generated and saved!")
                    st.session_state.wizard_step = 4
                    st.rerun()

        if st.button("⬅ Prev", key="s3_prev"):
            st.session_state.wizard_step = 2
            st.rerun()

        if st.session_state.course_full:
            st.markdown("### Preview (first 2000 characters)")
            st.write(st.session_state.course_full[:2000] + " ...")

    # STEP 4
    elif step == 4:
        st.subheader("Step 5: Course Preview, Modules & Videos")

        full_text = st.session_state.course_full
        modules = st.session_state.modules

        if not full_text:
            st.warning("No course loaded or generated yet.")
            if st.button("Go back to Generate"):
                st.session_state.wizard_step = 3
                st.rerun()
            return

        course_title = st.session_state.wizard_data.get("topic") or "Generated Course"

        # Course Preview (SAFE SLIDER)
        st.markdown("### 🔍 Course Preview")

        text_len = len(full_text)
        slider_min = 100
        slider_max = min(5000, text_len)

        if slider_max <= slider_min:
            preview_chars = slider_max
        else:
            preview_chars = st.slider(
                "Preview length (characters)",
                min_value=slider_min,
                max_value=slider_max,
                value=min(1500, slider_max),
                step=100,
            )

        st.text_area(
            "Preview",
            value=full_text[:preview_chars],
            height=200,
        )

        # Modules + YouTube links
        if modules:
            st.markdown("### 📚 Full Course by Modules")
            for i, m in enumerate(modules, start=1):
                title = m["title"] or f"Module {i}"
                desc = m["description"]
                st.markdown(f"#### {title}")
                st.write(desc)

                if st.session_state.wizard_data.get("include_video", "Yes") == "Yes":
                    yt = youtube_search_link(course_title, title)
                    st.markdown(
                        f"[✅ Watch recommended YouTube video for this completed module]({yt})"
                    )

            st.markdown("---")
        else:
            st.markdown("### Complete Course (Text)")
            st.write(full_text)

        # PDF download
        clean_text = strip_unsupported_chars(full_text)
        pdf_bytes = create_pdf(course_title, clean_text)

        st.download_button(
            label="📥 Download Complete Course as PDF",
            data=pdf_bytes,
            file_name=f"{course_title.replace(' ', '_')}.pdf",
            mime="application/pdf",
        )

        if st.button("⬅ Prev", key="s4_prev"):
            st.session_state.wizard_step = 3
            st.rerun()

# =========================
# MAIN
# =========================

def main():
    if st.session_state.screen == "auth":
        auth_screen()
    else:
        builder_screen()

if __name__ == "__main__":
    main()

