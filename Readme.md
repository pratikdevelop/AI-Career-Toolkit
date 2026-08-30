# AI Resume & Cover Letter Optimizer

A free, zero-cost AI app that scores a resume against a job description and
generates an optimized rewrite + tailored cover letter.

## Cost: $0
- Streamlit Community Cloud hosting: **free**
- Google Gemini API (gemini-1.5-flash): **free tier** — generous daily limits,
  no credit card required
- Each user brings their own free API key (see below) — this also means
  **you pay nothing even as usage scales**

---

## Step 1 — Get a free Gemini API key (2 minutes)
1. Go to https://aistudio.google.com/app/apikey
2. Sign in with any Google account
3. Click "Create API Key" — copy it somewhere safe

You'll paste this into the app's sidebar when using it. (For your own testing,
just use your own key.)

## Step 2 — Run it locally (optional, to test)
```bash
pip install -r requirements.txt
streamlit run app.py
```
It'll open at http://localhost:8501

## Step 3 — Deploy for free on Streamlit Community Cloud
1. Create a free GitHub account (if you don't have one) and a new public repo
2. Upload `app.py` and `requirements.txt` to that repo
3. Go to https://share.streamlit.io/ and sign in with GitHub
4. Click "New app" → select your repo → set main file to `app.py` → Deploy
5. You'll get a public URL like `https://your-app-name.streamlit.app`
   that anyone can use — for free, forever, on the free tier

## Step 4 (later) — Add your own key so users don't need one
Once you want to charge or reduce friction, you can:
- Store YOUR OWN API key as a Streamlit "secret" (Settings → Secrets on
  Streamlit Cloud) instead of asking users to paste their own
- This costs you nothing extra unless usage is very high, since Gemini's
  free tier covers a large number of requests/day
- At that point, add a simple paywall (e.g., Stripe Payment Links — free to
  set up, small % fee per transaction) before revealing results

## Monetization path from here
1. **Validate free** — share the public link, get 20-50 real users, collect
   feedback/testimonials
2. **Add pay-what-you-want** via a Stripe Payment Link (free to create)
   gating the "download" buttons
3. **Move to subscription** ($5-9/mo for unlimited optimizations) once you
   have repeat users
4. **Content marketing** — post before/after resume screenshots on
   LinkedIn/TikTok; this is your free distribution channel

## Notes on the code
- Uses `gemini-1.5-flash` — fast and fully covered by the free tier
- Prompts the model to return strict JSON so the app can render clean
  sections (score, keywords, suggestions, rewritten resume, cover letter)
- No resume data is stored anywhere — it only lives in the user's session