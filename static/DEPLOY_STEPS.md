# COTD v4 Visual Refresh — Deploy Steps

## What changed in this update

**Single file modified**: `static/index.html`

**New features:**
- ✅ Dark/Light theme toggle (🌙/☀️ button in header, persisted)
- ✅ Lite/Pro chart mode toggle (persisted)
- ✅ Lite: single close-price line with amber fade
- ✅ Pro: candles + MA(7)/MA(25)/MA(99) + volume (Binance-native)
- ✅ Sentiment panel shows bots only (not "real users today")
- ✅ Onboarding mandatory on first visit
- ✅ Full Binance color palette, Arial fonts
- ✅ All decorations (WOTD golden arcs) removed
- ✅ No "Continue in Binance app" CTA (COTD lives inside the app)

**Preserved** (not changed):
- All the JS game logic (SPA routing, timer, rounds, reveals)
- Scoring and verdict tiers (5 tiers still used)
- i18n (ES/EN/ZH)
- Dev bar (visible for demo)
- Auth token protection

## Deploy steps (from your Mac)

```bash
# 1. Go to your local repo
cd /Users/vandetoren/Documents/Vandetoren/candleeye/

# 2. Back up current version locally (safety)
cp static/index.html static/index.html.v3_backup

# 3. Replace with new version
# Copy the contents of the new index.html from the download

# 4. Quick local test (optional but recommended)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
ACCESS_TOKEN=test_local python server.py
# Open http://localhost:5000/?k=test_local
# Click around: onboarding shows first time, theme toggle works, Lite/Pro toggle works

# 5. Commit and push
git add static/index.html
git commit -m "v4 visual refresh: dark/light + Lite/Pro + Binance paleta"
git push

# Railway will auto-deploy. Watch the deploy log at railway.app.
# Once deployed, test in iPhone with:
# https://cotd.up.railway.app/?k=YOUR_ACCESS_TOKEN
```

## What to check in iPhone after deploy

**Home screen:**
- [ ] Header shows: help-btn (?) — theme-btn (🌙) — ES/EN/ZH
- [ ] Theme toggle button switches dark/light instantly
- [ ] Week grid shows days with amber highlight for wins
- [ ] CTA "Jugar ahora" is amber

**Onboarding (first visit):**
- [ ] If you clear localStorage, opening the page shows onboarding modal
- [ ] After clicking "Got it" / "Confirmar", it doesn't re-appear

**Play screen:**
- [ ] Header shows: ticker (●●●/USDC) — theme-btn — Lite|Pro — score
- [ ] Default mode is Lite (just a line, no candles, amber fade below)
- [ ] Click Pro → instant switch to candles + 3 MAs + volume
- [ ] Click Lite → instant switch back to just line
- [ ] Theme toggle during play works
- [ ] Timer counts down 10s
- [ ] Up/Down buttons work, decision triggers reveal

**Reveal screen:**
- [ ] Shows verdict + pct change + points
- [ ] You can still change Lite/Pro and theme during reveal
- [ ] Auto-advances to next round or summary

**Summary:**
- [ ] X/5 hero circle
- [ ] Weekly streak showing
- [ ] Share button works
- [ ] No "Continue in Binance app" CTA (removed intentionally)

## Rollback plan

If something breaks:

```bash
cd /Users/vandetoren/Documents/Vandetoren/candleeye/
cp static/index.html.v3_backup static/index.html
git add static/index.html
git commit -m "rollback to v3"
git push
```

## Known limitations (expected, for later)

- No Wordle model yet — charts still random per user (decision deferred)
- No ranking screen (decision deferred, mockup available to show)
- Server-side no changes (only `static/index.html` modified)
- Cache de SVG removed → slightly more CPU per render, but negligible on modern phones

## If meeting needs a quick recap

**What you show:**
1. Open URL on iPhone with your access token
2. Onboarding explains the game in 3 steps
3. Home shows today's week progress + CTA to play
4. Play the 5 rounds — show Lite/Pro toggle mid-round to demonstrate
5. Show dark/light toggle to demonstrate theme system
6. Reveal shows actual outcome + % move + points
7. Summary shows score + share card
8. Back to home

**Time needed: ~3-4 minutes for full demo.**

**Dev bar** lets you skip days and reset week if you need to demo multiple sessions.
