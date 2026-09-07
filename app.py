import streamlit as st
import google.generativeai as genai
import json
import re
import io
import requests
from bs4 import BeautifulSoup
import PyPDF2
import docx
from urllib.parse import quote

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="CareerReshape",
    page_icon="📄",
    layout="wide"
)

# =========================================================
# HELPER FUNCTIONS (defined first, used by both tool modes)
# =========================================================

@st.cache_data(show_spinner=False)
def parse_resume_file(file_bytes, file_name):
    """Extract plain text from an uploaded PDF, DOCX, or TXT file."""
    name = file_name.lower()

    if name.endswith(".pdf"):
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text.strip()

    elif name.endswith(".docx"):
        doc = docx.Document(io.BytesIO(file_bytes))
        text = "\n".join(p.text for p in doc.paragraphs)
        return text.strip()

    elif name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore").strip()

    else:
        raise ValueError("Unsupported file type. Please upload a PDF, DOCX, or TXT file.")


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_job_description(url):
    """Fetch and extract readable text from a job posting URL."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ResumeOptimizerBot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)

    # Trim overly long pages to keep prompt size reasonable
    return cleaned[:8000]


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_linkedin_profile(url):
    """Attempt to fetch a public LinkedIn profile page.

    LinkedIn aggressively blocks non-logged-in requests, so this frequently
    returns a login wall or bot-detection page instead of real content.
    Returns (text, looks_blocked) so the caller can show an honest message
    rather than silently passing junk to the AI model.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=10)

    if resp.status_code in (403, 999):
        return "", True

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)

    # Heuristic: LinkedIn's login/auth-wall pages are short and contain
    # these tells almost every time. Real profile pages are long and don't.
    blocked_signals = ["join linkedin", "sign in to view", "authwall", "join now"]
    looks_blocked = (
        len(cleaned) < 1500
        or any(signal in cleaned.lower() for signal in blocked_signals)
    )

    return cleaned[:8000], looks_blocked


def build_resume_docx(resume_text):
    """Turn plain resume text into a cleanly formatted Word document."""
    document = docx.Document()

    section = document.sections[0]
    section.top_margin = docx.shared.Inches(0.6)
    section.bottom_margin = docx.shared.Inches(0.6)
    section.left_margin = docx.shared.Inches(0.75)
    section.right_margin = docx.shared.Inches(0.75)

    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = docx.shared.Pt(11)

    lines = resume_text.split("\n")
    first_line_used_as_title = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            document.add_paragraph("")
            continue

        if not first_line_used_as_title:
            heading = document.add_heading(stripped, level=1)
            heading.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
            first_line_used_as_title = True
            continue

        if stripped.isupper() and len(stripped) < 40:
            document.add_heading(stripped.title(), level=2)
            continue

        if stripped.startswith(("-", "•", "*")):
            document.add_paragraph(stripped.lstrip("-•* ").strip(), style="List Bullet")
            continue

        document.add_paragraph(stripped)

    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


def build_resume_prompt(resume, job):
    return f"""
You are an expert resume writer and ATS (Applicant Tracking System) specialist.

Given the RESUME and JOB DESCRIPTION below, do the following and respond ONLY in valid JSON
(no markdown fences, no preamble):

{{
  "match_score": <integer 0-100, how well the resume matches the job description>,
  "missing_keywords": [<list of important keywords/skills from the job description missing in the resume>],
  "strengths": [<list of 3-5 things the resume already does well for this job>],
  "improvement_suggestions": [<list of 3-6 specific, actionable suggestions>],
  "optimized_resume": "<a rewritten, improved version of the resume text, tailored to this job, keeping it truthful to the original content — do not invent experience>",
  "cover_letter": "<a concise, tailored 3-paragraph cover letter based on the resume and job description>",
  "outreach_email_subject": "<a short, specific email subject line for applying to this role, e.g. 'Application for [Role] — [Candidate Name]'>",
  "outreach_email_body": "<a brief, direct application email (shorter than the cover letter, 3-4 short paragraphs), suitable for sending directly to a hiring contact, mentioning the attached resume>"
}}

RESUME:
{resume}

JOB DESCRIPTION:
{job}
"""


def build_linkedin_prompt(source_text, target_role):
    role_line = f"Target role/industry to tailor toward: {target_role}" if target_role else "No specific target role given — optimize for general career growth in the same field."
    return f"""
You are an expert LinkedIn profile writer and personal branding strategist.

Given the source content below (a resume or existing LinkedIn profile text), produce an
optimized LinkedIn profile. Respond ONLY in valid JSON (no markdown fences, no preamble):

{{
  "headline": "<a compelling LinkedIn headline, under 220 characters, keyword-rich>",
  "about_section": "<a 3-4 paragraph LinkedIn About section, written in first person, engaging and specific — not generic corporate language>",
  "experience_bullets": [<list of 5-8 rewritten, achievement-focused experience bullet points suitable for LinkedIn's Experience section, each starting with a strong action verb>],
  "skills_to_add": [<list of 8-12 relevant skills to add to the LinkedIn Skills section>],
  "improvement_notes": [<list of 3-5 specific tips on what was weak in the original and why the changes help>]
}}

{role_line}

SOURCE CONTENT:
{source_text}
"""


EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

def extract_email_from_text(text):
    """Find the first email address mentioned in a job posting's text, if any.

    Only detects emails the company itself chose to publish on the posting —
    never guesses, infers, or looks up an individual's personal email.
    """
    if not text:
        return None
    match = EMAIL_REGEX.search(text)
    return match.group(0) if match else None


def build_mailto_link(recipient, subject, body):
    return f"mailto:{quote(recipient)}?subject={quote(subject)}&body={quote(body)}"


def extract_json(text):
    # Strip markdown code fences if present
    text = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip("`").strip()
    return json.loads(text)


def get_json_response(model, prompt, retries=1):
    """Call the model and parse JSON, retrying once with a repair prompt if parsing fails."""
    response = model.generate_content(prompt)
    try:
        return extract_json(response.text)
    except json.JSONDecodeError:
        if retries <= 0:
            raise
        repair_prompt = (
            "Your previous response was not valid JSON. "
            "Return ONLY valid JSON, no markdown fences, no extra text. "
            f"Here was your response:\n\n{response.text}"
        )
        repaired = model.generate_content(repair_prompt)
        return extract_json(repaired.text)


@st.cache_data(show_spinner=False, ttl=3600)
def get_available_models(_api_key):
    """List models that currently support generateContent for this key.

    Falls back to a hardcoded guess list if discovery itself fails (e.g.
    transient network issue), so the app degrades instead of crashing.
    """
    fallback = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
    try:
        genai.configure(api_key=_api_key)
        names = []
        for m in genai.list_models():
            if "generateContent" in getattr(m, "supported_generation_methods", []):
                names.append(m.name.replace("models/", ""))
        flash = [n for n in names if "flash" in n]
        other = [n for n in names if n not in flash]
        ordered = flash + other
        return ordered if ordered else fallback
    except Exception:
        return fallback


def run_ai_json_call(api_key, prompt):
    """Shared model-selection + call logic used by both tools."""
    genai.configure(api_key=api_key)
    model_names = get_available_models(api_key)
    last_error = None
    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            return get_json_response(model, prompt)
        except Exception as model_err:
            last_error = model_err
            continue
    raise RuntimeError(f"None of the available Gemini models worked. Last error: {last_error}")


FREE_USES_PER_SESSION = 3

def check_and_consume_free_use():
    """Soft usage-cap paywall: tracks free uses in session state.

    Returns True if this use is allowed (consumes one credit), False if the
    free limit is reached. If no Stripe link is configured, the cap is not
    enforced at all — everything stays free until you set STRIPE_PAYMENT_LINK.
    """
    stripe_link = st.secrets.get("STRIPE_PAYMENT_LINK", None) if hasattr(st, "secrets") else None
    if not stripe_link:
        return True, None

    if "uses_this_session" not in st.session_state:
        st.session_state.uses_this_session = 0

    if st.session_state.uses_this_session >= FREE_USES_PER_SESSION:
        return False, stripe_link

    st.session_state.uses_this_session += 1
    return True, stripe_link


def show_paywall_message(stripe_link):
    st.warning(f"You've used your {FREE_USES_PER_SESSION} free optimizations for this session.")
    st.link_button("💳 Unlock unlimited optimizations", stripe_link, use_container_width=True)


def log_event(event_type, details=""):
    """Fire-and-forget analytics logging to a Google Sheet via Apps Script.

    Never raises — if the webhook isn't configured or the request fails,
    this silently does nothing so it can never break the app's main flow.
    """
    webhook_url = st.secrets.get("ANALYTICS_WEBHOOK_URL", None) if hasattr(st, "secrets") else None
    if not webhook_url:
        return
    try:
        requests.post(
            webhook_url,
            json={"event_type": event_type, "details": details},
            timeout=3
        )
    except Exception:
        pass


@st.cache_data(show_spinner=False, ttl=30)
def get_analytics_summary():
    """Read aggregate stats back from the analytics webhook, if configured."""
    webhook_url = st.secrets.get("ANALYTICS_WEBHOOK_URL", None) if hasattr(st, "secrets") else None
    if not webhook_url:
        return None
    try:
        resp = requests.get(webhook_url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


EXAMPLE_RESUME = """Jordan Lee
Marketing Coordinator with 3 years of experience in social media management and email campaigns.

Experience:
- Managed social media accounts for a 50-person retail company, growing followers by 40%
- Wrote and scheduled weekly email newsletters using Mailchimp
- Coordinated with design team on marketing assets
- Tracked campaign performance in spreadsheets

Skills: Social media, Mailchimp, Canva, basic Excel, team communication
Education: B.A. Communications, State University, 2021
"""

EXAMPLE_JOB = """Senior Digital Marketing Specialist

We're looking for a Senior Digital Marketing Specialist to lead our growth marketing efforts.

Responsibilities:
- Own paid and organic social media strategy across platforms
- Analyze campaign performance using Google Analytics and HubSpot
- Manage a $50k/month digital ad budget across Meta and Google Ads
- Lead A/B testing for email and landing page conversion
- Mentor junior marketing team members

Requirements:
- 5+ years digital marketing experience
- Proficiency in Google Analytics, HubSpot, and Meta Ads Manager
- Proven track record managing paid ad budgets
- Strong data analysis and reporting skills
"""

# =========================================================
# SIDEBAR: API KEY
# =========================================================
st.sidebar.title("⚙️ Setup")

api_key = st.secrets.get("GEMINI_API_KEY", None) if hasattr(st, "secrets") else None

if api_key:
    st.sidebar.success("✅ Using built-in API key — just upload and go!")
else:
    st.sidebar.markdown(
        """
        This app uses **Google Gemini's free API**.

        1. Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
        2. Paste it below (it's never stored)
        """
    )
    api_key = st.sidebar.text_input("Gemini API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.caption("CareerReshape · Built with ❤️. No data is saved after your session ends.")

# =========================================================
# HEADER + MODE SELECTOR
# =========================================================
st.title("📄 CareerReshape")
st.markdown("**Reshape your resume and LinkedIn profile for the job you actually want** — powered by AI.")

if "page_view_logged" not in st.session_state:
    log_event("page_view")
    st.session_state.page_view_logged = True

app_mode = st.radio(
    "Choose a tool",
    ["📄 Resume Optimizer", "💼 LinkedIn Profile Optimizer"],
    horizontal=True
)
st.markdown("---")

# =========================================================
# MODE 1: RESUME OPTIMIZER
# =========================================================
if app_mode == "📄 Resume Optimizer":

    if "example_loaded" not in st.session_state:
        st.session_state.example_loaded = False

    example_col, _ = st.columns([1, 3])
    with example_col:
        if st.button("✨ Try an example", use_container_width=True):
            st.session_state.example_loaded = True

    if st.session_state.example_loaded:
        st.info("Example resume and job description loaded below — click **Analyze & Optimize** to see it in action.")

    st.markdown("")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📤 Your Resume")
        resume_text = ""
        if st.session_state.example_loaded:
            resume_text = EXAMPLE_RESUME
            st.success("✅ Using example resume")
            with st.expander("Preview example resume"):
                st.text(resume_text)
        else:
            resume_file = st.file_uploader(
                "Upload your resume",
                type=["pdf", "docx", "txt"],
                help="PDF, Word (.docx), or plain text (.txt)"
            )
            if resume_file is not None:
                try:
                    file_bytes = resume_file.getvalue()
                    resume_text = parse_resume_file(file_bytes, resume_file.name)
                    if resume_text:
                        if len(resume_text) > 15000:
                            resume_text = resume_text[:15000]
                            st.warning("Resume was long — trimmed to the first 15,000 characters.")
                        st.success(f"✅ Loaded {resume_file.name} ({len(resume_text)} characters)")
                        with st.expander("Preview extracted text"):
                            st.text(resume_text[:2000] + ("..." if len(resume_text) > 2000 else ""))
                    else:
                        st.warning("Couldn't extract text from that file — it may be a scanned image PDF.")
                except Exception as e:
                    st.error(f"Error reading file: {e}")

    with col2:
        st.subheader("🔗 Job Description")
        job_desc = ""
        if st.session_state.example_loaded:
            job_desc = EXAMPLE_JOB
            st.success("✅ Using example job posting")
            with st.expander("Preview example job posting"):
                st.text(job_desc)
        else:
            job_input_mode = st.radio(
                "How do you want to provide the job posting?",
                ["From URL", "Paste text"],
                horizontal=True
            )

            if job_input_mode == "From URL":
                job_url = st.text_input(
                    "Job posting URL",
                    placeholder="https://company.com/careers/job-posting"
                )
                if job_url:
                    with st.spinner("Fetching job description..."):
                        try:
                            job_desc = fetch_job_description(job_url)
                            if job_desc:
                                st.success(f"✅ Fetched job posting ({len(job_desc)} characters)")
                                with st.expander("Preview fetched text"):
                                    st.text(job_desc[:2000] + ("..." if len(job_desc) > 2000 else ""))
                            else:
                                st.warning("Couldn't extract readable text from that page.")
                        except Exception as e:
                            st.error(f"Couldn't fetch that URL: {e}. Try 'Paste text' instead.")
            else:
                job_desc = st.text_area(
                    "Paste the job posting text here",
                    height=250,
                    placeholder="Paste the job description..."
                )

    analyze_btn = st.button("🚀 Analyze & Optimize", type="primary", use_container_width=True)

    if analyze_btn:
        if not api_key:
            st.error("⚠️ Please enter your free Gemini API key in the sidebar.")
        elif not resume_text.strip():
            st.error("⚠️ Please upload a resume file.")
        elif not job_desc.strip():
            st.error("⚠️ Please provide a job description (via URL or paste).")
        else:
            allowed, stripe_link = check_and_consume_free_use()
            if not allowed:
                show_paywall_message(stripe_link)
                st.stop()
            with st.spinner("Analyzing your resume against the job description..."):
                try:
                    prompt = build_resume_prompt(resume_text, job_desc)
                    result = run_ai_json_call(api_key, prompt)
                    log_event("resume_optimization_completed")

                    score = result.get("match_score", 0)
                    st.subheader("📊 Match Score")
                    st.progress(score / 100)
                    st.metric("ATS Match Score", f"{score}/100")

                    tab1, tab2, tab3, tab4, tab5 = st.tabs(
                        ["🔑 Keywords & Strengths", "💡 Suggestions", "📝 Optimized Resume", "✉️ Cover Letter", "📧 Outreach Email"]
                    )

                    with tab1:
                        st.markdown("**Missing Keywords**")
                        missing = result.get("missing_keywords", [])
                        if missing:
                            st.write(", ".join(f"`{kw}`" for kw in missing))
                        else:
                            st.success("No major keywords missing!")

                        st.markdown("**Strengths**")
                        for s in result.get("strengths", []):
                            st.markdown(f"- ✅ {s}")

                    with tab2:
                        st.markdown("**Improvement Suggestions**")
                        for i, s in enumerate(result.get("improvement_suggestions", []), 1):
                            st.markdown(f"{i}. {s}")

                    with tab3:
                        st.markdown("**Optimized Resume**")
                        optimized = result.get("optimized_resume", "")
                        st.text_area("Copy your optimized resume:", value=optimized, height=400)

                        docx_buffer = build_resume_docx(optimized)
                        dl_col1, dl_col2 = st.columns(2)
                        with dl_col1:
                            st.download_button(
                                "⬇️ Download as Word (.docx)",
                                docx_buffer,
                                file_name="optimized_resume.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True
                            )
                        with dl_col2:
                            st.download_button(
                                "⬇️ Download as Text (.txt)",
                                optimized,
                                file_name="optimized_resume.txt",
                                use_container_width=True
                            )

                    with tab4:
                        st.markdown("**Tailored Cover Letter**")
                        cover = result.get("cover_letter", "")
                        st.text_area("Copy your cover letter:", value=cover, height=300)
                        st.download_button(
                            "⬇️ Download Cover Letter (.txt)",
                            cover,
                            file_name="cover_letter.txt"
                        )

                    with tab5:
                        st.markdown("**Application Outreach Email**")
                        detected_email = extract_email_from_text(job_desc)
                        if detected_email:
                            st.success(f"✅ Found a contact email on this posting: {detected_email}")
                        else:
                            st.info(
                                "No email address was found on this job posting. "
                                "If you know the correct application contact, enter it below — "
                                "this app never guesses or looks up individual email addresses."
                            )

                        recipient = st.text_input(
                            "Recipient email",
                            value=detected_email or "",
                            placeholder="hr@company.com"
                        )
                        email_subject = st.text_input(
                            "Subject",
                            value=result.get("outreach_email_subject", "")
                        )
                        email_body = st.text_area(
                            "Body",
                            value=result.get("outreach_email_body", ""),
                            height=250
                        )

                        st.caption(
                            "📎 Remember to attach your downloaded resume before sending — "
                            "this only opens a draft in your own email client, it never sends anything for you."
                        )

                        if recipient.strip():
                            mailto_url = build_mailto_link(recipient.strip(), email_subject, email_body)
                            st.link_button("📧 Open draft in your email app", mailto_url, use_container_width=True)
                        else:
                            st.caption("Enter a recipient email above to enable the draft button.")

                except json.JSONDecodeError:
                    st.error("The AI response couldn't be parsed. Please try again.")
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

    st.markdown("---")
    st.caption("💡 Tip: For best results, use a job URL with the full posting (skills, responsibilities, requirements) visible on the page.")

# =========================================================
# MODE 2: LINKEDIN PROFILE OPTIMIZER
# =========================================================
else:
    st.markdown(
        "Paste your current LinkedIn profile text, or reuse a resume you already have. "
        "Get an optimized headline, About section, experience bullets, and skills to add."
    )

    li_col1, li_col2 = st.columns([2, 1])

    with li_col1:
        li_input_mode = st.radio(
            "Source content",
            [
                "Upload LinkedIn PDF export (recommended)",
                "Paste current LinkedIn profile",
                "From LinkedIn URL",
                "Upload a resume instead"
            ],
            horizontal=True
        )

        source_text = ""
        if li_input_mode == "Upload LinkedIn PDF export (recommended)":
            with st.expander("📋 How to export your LinkedIn profile as a PDF"):
                st.markdown(
                    """
                    1. Go to your LinkedIn profile page
                    2. Click **"More"** (below your profile photo/banner)
                    3. Select **"Save to PDF"**
                    4. Upload the downloaded file below

                    This is the most reliable option — it's your actual profile content,
                    directly from LinkedIn, with no scraping or blocking involved.
                    """
                )
            li_pdf_file = st.file_uploader(
                "Upload your LinkedIn PDF export",
                type=["pdf"],
                key="linkedin_pdf_uploader"
            )
            if li_pdf_file is not None:
                try:
                    file_bytes = li_pdf_file.getvalue()
                    source_text = parse_resume_file(file_bytes, li_pdf_file.name)
                    if source_text:
                        if len(source_text) > 15000:
                            source_text = source_text[:15000]
                            st.warning("Profile export was long — trimmed to the first 15,000 characters.")
                        st.success(f"✅ Loaded {li_pdf_file.name} ({len(source_text)} characters)")
                        with st.expander("Preview extracted text"):
                            st.text(source_text[:2000] + ("..." if len(source_text) > 2000 else ""))
                    else:
                        st.warning("Couldn't extract text from that PDF.")
                except Exception as e:
                    st.error(f"Error reading file: {e}")
        elif li_input_mode == "Paste current LinkedIn profile":
            source_text = st.text_area(
                "Paste your current headline, About section, and/or experience bullets",
                height=280,
                placeholder="Paste whatever you currently have on your LinkedIn profile..."
            )
        elif li_input_mode == "From LinkedIn URL":
            st.caption(
                "⚠️ LinkedIn blocks nearly all automated fetches, even for public profiles — "
                "'Upload LinkedIn PDF export' above is far more reliable. This will still try."
            )
            li_url = st.text_input(
                "LinkedIn profile URL",
                placeholder="https://www.linkedin.com/in/your-profile"
            )
            if li_url:
                with st.spinner("Attempting to fetch profile..."):
                    try:
                        fetched_text, looks_blocked = fetch_linkedin_profile(li_url)
                        if looks_blocked or not fetched_text:
                            st.error(
                                "LinkedIn blocked this fetch (this is expected — it blocks "
                                "almost all non-logged-in requests). Please use the "
                                "'Upload LinkedIn PDF export' option instead."
                            )
                        else:
                            source_text = fetched_text
                            st.success(f"✅ Fetched profile content ({len(source_text)} characters) — please verify it looks correct below.")
                            with st.expander("Preview fetched text"):
                                st.text(source_text[:2000] + ("..." if len(source_text) > 2000 else ""))
                    except Exception as e:
                        st.error(f"Couldn't fetch that URL: {e}. Please use 'Upload LinkedIn PDF export' instead.")
        else:
            li_resume_file = st.file_uploader(
                "Upload your resume",
                type=["pdf", "docx", "txt"],
                key="linkedin_resume_uploader"
            )
            if li_resume_file is not None:
                try:
                    file_bytes = li_resume_file.getvalue()
                    source_text = parse_resume_file(file_bytes, li_resume_file.name)
                    if source_text:
                        if len(source_text) > 15000:
                            source_text = source_text[:15000]
                            st.warning("Resume was long — trimmed to the first 15,000 characters.")
                        st.success(f"✅ Loaded {li_resume_file.name} ({len(source_text)} characters)")
                    else:
                        st.warning("Couldn't extract text from that file — it may be a scanned image PDF.")
                except Exception as e:
                    st.error(f"Error reading file: {e}")

    with li_col2:
        target_role = st.text_input(
            "Target role/industry (optional)",
            placeholder="e.g. Senior Product Manager, fintech"
        )
        st.caption("Leave blank to optimize generally rather than for a specific role.")

    li_analyze_btn = st.button("🚀 Optimize My LinkedIn Profile", type="primary", use_container_width=True)

    if li_analyze_btn:
        if not api_key:
            st.error("⚠️ Please enter your free Gemini API key in the sidebar.")
        elif not source_text.strip():
            st.error("⚠️ Please paste your profile text or upload a resume.")
        else:
            allowed, stripe_link = check_and_consume_free_use()
            if not allowed:
                show_paywall_message(stripe_link)
                st.stop()
            with st.spinner("Optimizing your LinkedIn profile..."):
                try:
                    prompt = build_linkedin_prompt(source_text, target_role)
                    result = run_ai_json_call(api_key, prompt)
                    log_event("linkedin_optimization_completed")

                    li_tab1, li_tab2, li_tab3, li_tab4 = st.tabs(
                        ["✨ Headline", "📝 About Section", "💼 Experience Bullets", "🏷️ Skills & Notes"]
                    )

                    with li_tab1:
                        headline = result.get("headline", "")
                        st.text_area("Copy your new headline:", value=headline, height=80)

                    with li_tab2:
                        about = result.get("about_section", "")
                        st.text_area("Copy your new About section:", value=about, height=300)

                    with li_tab3:
                        st.markdown("**Rewritten Experience Bullets**")
                        for b in result.get("experience_bullets", []):
                            st.markdown(f"- {b}")

                    with li_tab4:
                        st.markdown("**Skills to Add**")
                        skills = result.get("skills_to_add", [])
                        if skills:
                            st.write(", ".join(f"`{s}`" for s in skills))
                        st.markdown("**Why These Changes Help**")
                        for n in result.get("improvement_notes", []):
                            st.markdown(f"- {n}")

                except json.JSONDecodeError:
                    st.error("The AI response couldn't be parsed. Please try again.")
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

    st.markdown("---")
    st.caption("💡 Tip: LinkedIn headlines perform best under 220 characters and front-load your role + key skill.")

# =========================================================
# HIDDEN ADMIN VIEW — only visible with ?admin=<ADMIN_KEY> in the URL
# =========================================================
query_params = st.query_params
admin_key = st.secrets.get("ADMIN_KEY", None) if hasattr(st, "secrets") else None

if admin_key and query_params.get("admin") == admin_key:
    st.markdown("---")
    st.header("📊 Admin: Usage Analytics")

    stats = get_analytics_summary()
    if stats is None:
        st.info("No analytics data yet, or ANALYTICS_WEBHOOK_URL isn't configured.")
    else:
        col_a, col_b = st.columns(2)
        col_a.metric("Total events (all time)", stats.get("total_events", 0))
        col_b.metric("Events today", stats.get("events_today", 0))

        st.markdown("**Breakdown by event type**")
        counts = stats.get("counts_by_type", {})
        if counts:
            for event_type, count in sorted(counts.items(), key=lambda x: -x[1]):
                st.markdown(f"- `{event_type}`: {count}")
        else:
            st.caption("No events logged yet.")

    if st.button("🔄 Refresh stats"):
        get_analytics_summary.clear()
        st.rerun()