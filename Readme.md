# CareerReshape

A free, zero-cost AI app with two tools:
1. **Resume Optimizer** — scores your resume against a job posting and
   generates an ATS-optimized rewrite + tailored cover letter
2. **LinkedIn Profile Optimizer** — rewrites your headline, About section,
   and experience bullets for LinkedIn

## Cost: $0 to run
- Streamlit Community Cloud hosting: **free**
- Google Gemini API: **free tier** — model selection auto-discovers whatever
  Gemini currently supports for your key, so it won't break when Google
  renames or retires model versions
- You provide one shared API key via Streamlit secrets — visitors don't
  need their own

---

## Step 1 — Get a free Gemini API key (2 minutes)
1. Go to https://aistudio.google.com/app/apikey
2. Sign in with any Google account
3. Click "Create API Key" — copy it somewhere safe

## Step 2 — Add your Gemini key as a Streamlit secret
**On Streamlit Cloud (for the live deployed app):**
1. Go to your app on https://share.streamlit.io/ → **⋮** menu → **Settings** → **Secrets**
2. Paste in:
   ```toml
   GEMINI_API_KEY = "your-actual-key-here"
   ```
3. Save — the app restarts automatically and picks it up

**For local testing:**
1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
2. Fill in your real key
3. **Never commit `secrets.toml` to GitHub**

Once set, the sidebar shows "✅ Using built-in API key" and visitors skip
straight to using the tool.

## Step 3 — (Optional) Add a Stripe paywall
The app includes a built-in soft paywall: 3 free optimizations per browser
session, then a Stripe payment link to unlock unlimited use. **It's off by
default** — nothing is gated until you set this secret.

1. Create a free Stripe account at https://stripe.com
2. Create a Payment Link (Stripe dashboard → Payment Links → free to create,
   Stripe only takes a % fee per actual transaction)
3. Add it as a secret alongside your Gemini key:
   ```toml
   GEMINI_API_KEY = "your-actual-key-here"
   STRIPE_PAYMENT_LINK = "https://buy.stripe.com/your-link"
   ```
4. Save — the app will now cap free users at 3 uses per session and show
   an "Unlock unlimited optimizations" button pointing to your Stripe link

This is a soft, session-based cap — it doesn't track users across sessions
or devices. Good enough for early validation; a real subscription/login
system is a later step once you have paying users to justify the extra
complexity.

## Step 4 — Run it locally (optional, to test)
```bash
pip install -r requirements.txt
streamlit run app.py
```
It'll open at http://localhost:8501

## Step 5 — Deploy for free on Streamlit Community Cloud
1. Create a free GitHub account (if you don't have one) and a new public repo
2. Upload `app.py` and `requirements.txt` to that repo (do **not** upload `secrets.toml`)
3. Go to https://share.streamlit.io/ and sign in with GitHub
4. Click "New app" → select your repo → set main file to `app.py`
5. **Custom URL**: in the "App URL" field during setup, choose a slug like
   `careerreshape` so your app lives at `https://careerreshape.streamlit.app`
   (subject to availability — Streamlit URLs are first-come, first-served)
6. Deploy, then add your secrets as described in Steps 2 and 3

## Cost note on sharing your own key
Gemini's free tier has a daily request quota shared across everyone using
your key. Fine for early testing and modest traffic; if usage grows, watch
your quota in Google AI Studio. The Stripe paywall above helps manage this
once real usage picks up.

## Monetization path from here
1. **Validate free** — share the public link, get 20-50 real users, collect
   feedback/testimonials
2. **Turn on the Stripe paywall** (Step 3 above) once you have signal that
   people find it valuable enough to hit the free cap
3. **Move to subscription** ($5-9/mo for unlimited optimizations) once you
   have repeat users
4. **Content marketing** — post before/after resume and LinkedIn screenshots
   on LinkedIn/TikTok; this is your free distribution channel

## Notes on the code
- Model selection calls `genai.list_models()` live and picks whatever
  currently supports `generateContent`, with a hardcoded list as a fallback
  only if discovery itself fails
- Prompts the model to return strict JSON, with one automatic retry if the
  model returns malformed JSON on the first try
- No resume or profile data is stored anywhere — it only lives in the
  user's browser session
- **Resume input**: file uploader accepting PDF, DOCX, or TXT
- **Job description input**: paste a job posting URL (auto-fetched) or
  paste the text directly
- **LinkedIn input**: upload a LinkedIn "Save to PDF" export (recommended
  — LinkedIn blocks most automated URL fetches), paste profile text
  directly, attempt a URL fetch (unreliable, kept as a last resort), or
  reuse an uploaded resume
- Resume/profile text is capped at 15,000 characters to keep prompts
  reasonable; fetched job/profile pages capped at 8,000 characters
- Optimized resumes can be downloaded as a formatted `.docx` or plain `.txt`
- Note: scanned/image-only PDFs won't extract text (no OCR) — the app warns
  when extraction comes back empty