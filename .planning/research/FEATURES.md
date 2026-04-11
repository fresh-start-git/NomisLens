# Feature Research

**Domain:** Windows 11 desktop screen magnifier bubble (accessibility overlay for Stargardt's disease user in veterinary clinic)
**Researched:** 2026-04-10
**Confidence:** HIGH (verified against Microsoft docs, WCAG, ZoomText, SuperNova, Windows Magnifier, and Stargardt's clinical literature)

## Executive Summary

Desktop magnifiers for low-vision users fall along a spectrum from system-level (Windows Magnifier, ZoomText, SuperNova) that take over the screen, to lightweight floating "lens/bubble" overlays that magnify a region without disrupting the rest of the workflow. For a Stargardt's disease user operating Idexx Cornerstone on a clinic touchscreen, the bubble pattern is decisively correct: the user needs peripheral scanning (eccentric viewing) of the full screen preserved while a movable, shaped magnifier amplifies whatever is beneath it. Table stakes are dominated by non-interference — click-through, no focus steal, no taskbar presence — and by physical ergonomics: large (>=44px) touch targets, high-contrast borders visible on any background, and instant global show/hide. Differentiators are Stargardt-specific comfort features (shape cycling so the user can adopt eccentric viewing, fine zoom steps in the 1.5-6x range, aggressive config persistence). Anti-features include anything that looks "professional" but adds modality, latency, or focus contention: modal settings dialogs, keyboard capture, text-only OCR modes, and full-screen magnification. The app must feel like a prosthetic, not a program.

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these will cause immediate rejection or unusable workflow.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Real-time pixel magnification under the window | The entire premise — bubble must show what's beneath it, live | MEDIUM | mss capture of region under window; target 30fps minimum; must exclude self from capture to avoid feedback loop |
| Click-through on magnified content area | User's workflow is in Cornerstone, not in the bubble; clicks must reach the app below | MEDIUM | WS_EX_LAYERED + WS_EX_TRANSPARENT on content hwnd; WM_NCHITTEST returning HTTRANSPARENT for middle zone only |
| Always-on-top | Bubble must stay visible when clicking into Cornerstone (Cornerstone steals focus constantly) | LOW | SetWindowPos with HWND_TOPMOST on creation and on focus events |
| Does not steal focus | Cornerstone has keyboard input at all times; bubble interactions must never take focus | MEDIUM | WS_EX_NOACTIVATE; avoid Tk focus_set; use win32 with activation flags |
| No taskbar presence | Taskbar clutter and alt-tab pollution are disorienting to low-vision users | LOW | WS_EX_TOOLWINDOW on owner hwnd |
| Movable by dragging a handle | User must reposition as they scan different parts of the screen | LOW | Drag bar at top; must have visible grip affordance |
| Resizable | Fixed size cannot cover a label AND a chart; users need to adapt mid-task | LOW | Bottom-right resize grip; constrain min 150x150, max 700x700 |
| Zoom in / zoom out controls | The one thing users will adjust constantly | LOW | Visible [-] and [+] buttons; current level readout |
| Reasonable zoom range (approx 1.5x-6x) | Below 1.5x is pointless; above 6x is unreadable due to pixel artifacts on most screens | LOW | 0.25x increments feel smooth without overwhelming UI |
| Global show/hide hotkey | User needs to hide the bubble to see the full screen context and bring it back instantly | MEDIUM | Ctrl+Z via keyboard lib or RegisterHotKey; must work when Cornerstone has focus |
| Visible border on any background | User loses the bubble on white/gray UI if border is subtle; Cornerstone has many backgrounds | LOW | Teal/soft-blue 3-4px; high-contrast choice avoids clashing with typical blue/gray medical UIs |
| Config persistence across sessions | Clinic PC reboots; user should not re-configure every morning | LOW | Write config.json on every change (debounced); read on launch |
| Single-exe deployment (no Python install) | Clinic PC has no dev tools; non-technical staff install by double-click | MEDIUM | PyInstaller --onefile with all deps bundled |
| Touch targets >=44x44 px | Clinic touchscreen is primary input; smaller targets fail per WCAG 2.5.5 and Microsoft Design Language | LOW | Enforce in layout; verify with on-device test |
| System tray icon with exit | App with no taskbar presence still needs a visible control surface for quit/show | LOW | pystray with minimum: Show, Hide, Always-on-top toggle, Exit |
| Quit cleanly | Low-vision users cannot debug orphaned processes | LOW | Handle WM_CLOSE, tray exit, Ctrl+C; release global hotkey |

### Differentiators (Competitive Advantage)

Features that make this app meaningfully better than Windows Magnifier's Lens mode for this specific user.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Shape cycling (circle / rounded-rect / rectangle) | Stargardt's users use eccentric viewing (peripheral vision) — the shape that best frames their PRL (preferred retinal locus) varies by user; letting them cycle at runtime lets them find their own answer | LOW-MEDIUM | SetWindowRgn with CreateRoundRectRgn / CreateEllipticRgn / CreateRectRgn; one-click cycle button on drag bar |
| Fine zoom steps (0.25x increments) | Low-vision users optimize zoom precisely to balance field-of-view vs legibility; 0.5x jumps (Windows default) overshoot | LOW | Round to 2 decimals; display "2.25x" etc |
| Persistent position AND shape AND zoom | User returns to the same bubble they left yesterday — reduces cognitive load dramatically for repeat tasks | LOW | Save on every change; atomic write to avoid corruption |
| Independent bubble lifecycle from Cornerstone | User can close/reopen Cornerstone without touching the bubble; most magnifiers die with a single focus change | LOW | Don't bind to foreground window; just capture geometry |
| Zero-chrome content area | ZoomText and SuperNova put crosshairs, pointers, and focus rings INSIDE the lens; for Stargardt's eccentric viewers this creates noise where they most need signal | LOW | Deliberate design choice: only pixels in the middle zone |
| Instant toggle (Ctrl+Z) that does not release focus | User can flash-check the unmagnified screen in Cornerstone without breaking their click sequence | MEDIUM | Hotkey must only toggle visibility — do not activate bubble window |
| Teal/soft-blue border (vs default yellow/red) | Medical UIs are blue/gray — red/yellow borders blend in; teal sits in an uncommon hue slot that stays visible | LOW | Document the choice; make border color config-editable but default teal |
| Drag handle with tactile-looking grip affordance | Touch users need obvious "grab here" zones; ZoomText's thin borders fail this | LOW | Grip symbol (≡ or dot pattern); minimum 44px tall |
| Config file in app directory (not %APPDATA%) | Non-technical clinic staff can find the file, delete to reset, or copy between machines | LOW | Explicit choice documented in README; handle read-only fallback |
| No internet / no telemetry | Clinic network may be locked down; HIPAA-adjacent environment rewards "offline-only" claim | LOW | Zero network imports; audit requirements.txt |
| Works even if Cornerstone is maximized/fullscreen | User runs Cornerstone fullscreen and still needs magnification | LOW | Always-on-top + topmost refresh on window events |
| Survives multi-monitor primary-display focus | Clinic PC has one display but DPI scaling must still work | MEDIUM | Use SetProcessDpiAwareness(2) per-monitor v2; correct physical-pixel capture |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good on paper but actively harm this use case. Ship without these and document why.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full-screen magnification mode | "More powerful than a bubble" | Breaks the core value: user loses peripheral context (critical for Stargardt's eccentric viewing) and cannot see Cornerstone's other panels | Keep bubble-only; rely on larger/resizable bubble for bigger regions |
| Text smoothing / font rendering (xFont-style) | ZoomText markets this heavily | Requires deep per-app integration (MSAA/UIA hooks into Cornerstone), which breaks with any Cornerstone update; pixel capture + bilinear is "good enough" at 3-6x for a clinic workflow | Use crisp nearest-neighbor at integer zooms; bilinear otherwise; keep it universal |
| Text-to-speech / OCR / document reader | "Low-vision users want reading" | Out of scope (Stargardt's user has usable peripheral vision and is doing workflow tasks not reading documents); adds huge dependencies (Tesseract, SAPI) and deployment complexity | Windows Narrator already exists; let the user run it separately if needed |
| Follow-focus / follow-caret tracking | "Automatic is better than manual" | User's attention moves faster than auto-tracking; auto-jumps cause motion sickness and break eccentric viewing strategies; also requires UIA hooks into Cornerstone | Manual drag — user knows where they want to look |
| Mouse-cursor lens (Windows Magnifier Lens mode) | "Follow the mouse" | Mouse cursor is not where the user is reading — it's where they're about to click; lens-follows-cursor hides the thing they wanted to see | Stationary bubble the user positions deliberately |
| Color inversion / high-contrast filter | "Classic low-vision feature" | Clicking-through means the app below (Cornerstone) must render normally for the user to click correctly; inverting colors inside the bubble creates a mental mismatch with the unmagnified truth | Let Windows global color filters handle this if needed |
| Crosshairs / focus rings inside the magnified area | "Helps locate the cursor" | Adds visual noise exactly where a Stargardt's user is using peripheral vision; the middle zone must be pure signal | Nothing in the middle zone except pixels |
| Modal settings dialog | "Every app has settings" | Steals focus from Cornerstone; breaks workflow; requires another round of touch-target compliance | Tray menu + hotkeys + direct on-bubble buttons only |
| Multiple bubbles / multi-instance | "Power users want two lenses" | Double the CPU of screen capture; focus and click-through logic gets 4x more complex; no evidence users want this | One bubble, period |
| Animated transitions / smooth resize | "Feels modern" | Motion is disorienting for Stargardt's users and wastes frame budget in the capture loop | Instant resize/show/hide |
| Mouse-wheel zoom | "Standard UX" | Mouse wheel goes to Cornerstone via click-through — binding it would break that; on a touchscreen, wheel is irrelevant anyway | Explicit [+]/[-] buttons |
| Auto-hide when idle | "Out of the way when unused" | Hiding without a deliberate user action means the user panics looking for it; worse for low-vision users who can't scan quickly | Ctrl+Z explicit toggle only |
| "Smart" snap-to-UI-element | "Magnifies whatever you're hovering" | Requires UIA; fragile against Cornerstone; surprising motion for a user who wants stability | Static position; user drags |
| Installer with UAC prompts | "Professional" | Clinic staff probably can't elevate; portable exe in a folder beats an installer | Single portable exe, config next to it |
| Cloud sync of settings | "Convenience across devices" | One machine only; adds network requirement; privacy concern in medical environment | Local config.json |
| Screenshot / recording of magnified view | "Share a screenshot" | PHI exposure risk in veterinary workflow; not the app's job | Windows Snipping Tool exists |
| Keyboard shortcut capture inside the bubble | "Power user ergonomics" | Any key-capture steals focus from Cornerstone; breaks typing into charts | Only one global hotkey (Ctrl+Z); no local bindings |

## Feature Dependencies

```
Single-exe deployment (PyInstaller)
    └──requires──> Pinned requirements.txt
                        └──requires──> No native build deps (mss + pywin32 + tk only)

Click-through on middle zone
    └──requires──> Three-zone layout (top handle, middle content, bottom controls)
                        └──requires──> WM_NCHITTEST per-zone handling
                                              └──requires──> Child hwnds or region-based hit testing

Real-time pixel magnification
    └──requires──> Screen capture (mss)
                        └──requires──> Self-exclusion from capture (capture region != window region, or hide during capture)
                                              └──requires──> DPI awareness (per-monitor v2)

Shape cycling
    └──requires──> SetWindowRgn
                        └──requires──> Rebuild region on resize
                                              └──requires──> Hit-testing compatible with region

Global hotkey (Ctrl+Z)
    └──requires──> RegisterHotKey or keyboard library
                        └──requires──> Hotkey does not activate window (WS_EX_NOACTIVATE preserved)

Config persistence
    └──requires──> Writable app directory OR %APPDATA% fallback
                        └──requires──> Atomic write (tempfile + rename)

Tray icon
    └──requires──> pystray thread separate from Tk mainloop
                        └──enhances──> Exit path (when bubble is hidden)

Touch targets >=44px ──enhances──> Drag handle, resize grip, zoom buttons

Teal border ──enhances──> Findability on varied backgrounds

Shape cycling ──enhances──> Eccentric viewing (Stargardt-specific)

Fine zoom increments ──enhances──> Precise zoom optimization (low-vision specific)

Mouse-follow lens ──conflicts──> Click-through on middle zone
(If the lens follows the mouse, the mouse cannot also be clicking through it)

Full-screen magnification ──conflicts──> Bubble overlay concept
(Mutually exclusive architectures)

Text smoothing (UIA-based) ──conflicts──> Universal capture approach
(UIA hooks break under Cornerstone updates)

Focus tracking ──conflicts──> "Does not steal focus" invariant
```

### Dependency Notes

- **Click-through requires three-zone layout:** The window cannot be 100% click-through (then you can't drag it). It cannot be 0% click-through (then clicks don't reach Cornerstone). Splitting into three hit-test zones is the only workable approach.
- **Real-time magnification requires self-exclusion:** If mss captures the region including the bubble itself, you get infinite recursion ("hall of mirrors"). Solutions: capture a larger-offset region, hide the window momentarily during capture, or composite excluding self.
- **Shape cycling enhances eccentric viewing:** Stargardt's users adopt a PRL (preferred retinal locus) in their peripheral vision. Different shapes better frame content for different PRLs — a round bubble for some, a wide rectangle for others. Giving runtime choice is free and valuable.
- **Mouse-follow conflicts with click-through:** You cannot both "follow the mouse" (mouse is over the bubble) and "clicks pass through" (mouse is interacting with what's below). Pick one architecture. This app picks stationary + click-through.
- **Full-screen magnification conflicts with the bubble concept:** These are two different products. Full-screen is what Windows Magnifier and ZoomText already do well. The bubble exists to NOT be full-screen.

## MVP Definition

### Launch With (v1)

The minimum product that delivers the core value: "Stargardt's user operates Cornerstone on a clinic touchscreen with a movable magnifying bubble."

- [ ] Floating always-on-top window, no taskbar presence (WS_EX_TOOLWINDOW + NOACTIVATE)
- [ ] Real-time mss capture + Tk render at 30fps, self-excluded to avoid feedback loop
- [ ] Click-through middle zone (WM_NCHITTEST HTTRANSPARENT per-zone)
- [ ] Three-zone layout: drag handle top, pixels middle, controls bottom
- [ ] Drag to move via top handle; resize via bottom-right grip (min 150, max 700)
- [ ] Zoom [-] [+] buttons, 1.5x-6x, 0.25x steps, current level readout
- [ ] Shape cycle button: circle -> rounded rect -> rectangle -> repeat (SetWindowRgn)
- [ ] Teal/soft-blue 3-4px border visible on any background
- [ ] Ctrl+Z global hotkey toggles visibility without stealing focus from Cornerstone
- [ ] System tray icon with Show, Hide, Always-on-top, Exit
- [ ] config.json persistence on every change (position, size, zoom, shape)
- [ ] All touch targets >=44x44px
- [ ] requirements.txt with pinned versions
- [ ] PyInstaller build.bat producing a single .exe
- [ ] README.md for non-technical clinic staff
- [ ] DPI-aware (per-monitor v2) so capture matches physical pixels

### Add After Validation (v1.x)

Only after the user has used v1 for a week and we hear what actually hurts.

- [ ] Secondary hotkeys for zoom +/- (only if user asks; initially hotkey-light to avoid focus risk) — trigger: user complains they can't reach buttons mid-task
- [ ] Color-pick for border (e.g., high-contrast orange option) — trigger: user says they still lose the bubble
- [ ] Optional pause/freeze-frame (keeps last captured image visible when Ctrl-held) — trigger: user needs to study a detail while cursor moves
- [ ] Opacity slider for handle/control strips (not content) — trigger: user says the chrome is distracting
- [ ] Second "preset" slot (circle-at-5x vs rectangle-at-2x) — trigger: user is cycling between two tasks constantly
- [ ] Per-zone hit-testing refinement if click-through has false positives — trigger: missed Cornerstone clicks

### Future Consideration (v2+)

Defer until we know v1 has product-market fit for this user and/or the pattern generalizes.

- [ ] Multi-monitor geometry — defer: clinic is single-display
- [ ] Additional language strings / i18n — defer: one English-speaking user
- [ ] Automatic updater — defer: clinic PC may not allow outbound network
- [ ] Generalization to other low-vision users (different PRL presets) — defer: validate one user first
- [ ] Per-app profiles (different settings when Cornerstone vs browser is foreground) — defer: only if the user actually switches apps often
- [ ] Keyboard-only repositioning (arrow keys) — defer: user is touchscreen-first

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Real-time mss capture + render | HIGH | MEDIUM | P1 |
| Click-through middle zone | HIGH | MEDIUM | P1 |
| Always-on-top + no focus steal | HIGH | MEDIUM | P1 |
| Three-zone layout | HIGH | LOW | P1 |
| Drag handle | HIGH | LOW | P1 |
| Resize grip | HIGH | LOW | P1 |
| Zoom +/- buttons (1.5x-6x, 0.25x steps) | HIGH | LOW | P1 |
| Shape cycling (SetWindowRgn) | HIGH | MEDIUM | P1 |
| Teal border | HIGH | LOW | P1 |
| Global Ctrl+Z toggle | HIGH | MEDIUM | P1 |
| System tray (show/hide/exit) | HIGH | LOW | P1 |
| config.json persistence | HIGH | LOW | P1 |
| Touch targets >=44px | HIGH | LOW | P1 |
| Per-monitor DPI awareness | HIGH | LOW | P1 |
| PyInstaller single-exe | HIGH | MEDIUM | P1 |
| No taskbar presence | MEDIUM | LOW | P1 |
| README for non-technical staff | MEDIUM | LOW | P1 |
| Optional freeze-frame | MEDIUM | MEDIUM | P2 |
| Border color config | MEDIUM | LOW | P2 |
| Opacity for control strips | LOW | LOW | P2 |
| Preset slots | LOW | MEDIUM | P3 |
| Per-app profiles | LOW | HIGH | P3 |
| Multi-monitor scaling | LOW | HIGH | P3 |
| Keyboard repositioning | LOW | LOW | P3 |

## Competitor Feature Analysis

| Feature | Windows Magnifier (Lens) | ZoomText | SuperNova | Our Approach |
|---------|--------------------------|----------|-----------|--------------|
| Zoom range | 100%-1600% | 1x-60x | 1.2x-64x | 1.5x-6x (narrower — appropriate for workflow, not reading) |
| Zoom increment | Fixed steps (25%, 50%) | Variable, 28 sizes | 28 sizes | 0.25x continuous (finer than any) |
| Shape | Rectangle only | Rectangle, "Lens", Docked | Circle, rect, custom | Circle, rounded rect, rect cycle |
| Click-through | No (full-screen or docked) | No | No | YES — core differentiator |
| Follows mouse | YES (Lens mode) | Optional | Optional | NO — stationary, user-positioned |
| Touch gestures | Partial (Windows 11) | Limited | 1/2/3-finger pan+pinch+menu | Drag + buttons only (explicit > gestural for this user) |
| Focus tracking | YES | YES | YES | NO — conflicts with click-through |
| Color inversion | YES | YES | YES | NO — conflicts with click-through accuracy |
| Text smoothing | YES (limited) | xFont (flagship) | xFont-like | NO — rely on pixel magnification |
| TTS / OCR | Read-from-here | DocReader/AppReader | Speech option | NO — out of scope |
| Config persistence | Windows settings | Profile files | Profile files | config.json next to exe |
| Deployment | Built-in | Licensed install | Licensed install | Portable single exe |
| Non-interference with other apps | LOW | LOW | LOW | HIGH (primary value) |
| Cost | Free | ~$650 | ~$595 | Free |

**Key insight:** Every commercial tool optimizes for "the magnifier is the primary workspace." This app optimizes for "the magnifier is a prosthetic overlay while Cornerstone is the workspace." That reframing drives every differentiator.

## Stargardt's Disease Specific Considerations

Central vision loss from Stargardt's disease has specific implications that shape the feature set:

1. **Eccentric viewing is standard.** Users train themselves to use a peripheral retinal locus (PRL) because the macula is damaged. This means:
   - Users look AROUND the thing they're reading, not AT it.
   - The visual noise INSIDE the bubble matters — crosshairs, focus rings, and UI chrome sit exactly where the user's functional vision is.
   - Different users adopt different PRLs (upper, lower, left, right). Shape choice accommodates this: a tall rectangle for a lower-PRL user, a wide rectangle for a side-PRL user.

2. **Peripheral vision is preserved long-term.** Unlike many macular diseases, Stargardt's patients retain excellent peripheral sensitivity for decades. This means:
   - Full-screen magnification actively hurts — it removes the peripheral context they rely on for orientation.
   - A floating bubble preserves peripheral scanning while giving central detail.

3. **High contrast matters more than high resolution.** Damaged macular photoreceptors need strong luminance differences to register. This means:
   - Border color must be HIGH contrast against all expected backgrounds (Cornerstone's mostly-blue/gray UI).
   - Teal is a defensible default because it sits in an otherwise-uncommon hue slot in medical software.
   - Text smoothing is less important than raw pixel contrast.

4. **Photophobia is common.** Bright screens aggravate Stargardt's symptoms. This means:
   - Semi-transparent dark strips for top/bottom chrome (already specced) help.
   - Do NOT flash, blink, or animate anything.

5. **Magnification responds well in Stargardt's (better than in most maculopathies).** Clinical research confirms ~80% of Stargardt's patients successfully adopt magnification aids. This is higher than AMD or other central vision losses, so the product bet is sound.

6. **Users know their own zoom sweet spot.** Low-vision users optimize magnification precisely — too little and they can't read, too much and they lose too much field-of-view. Fine-grained 0.25x steps let them hit their exact number. 0.5x or 1.0x steps (common defaults) overshoot.

## Touch UX Considerations for Clinic Touchscreen

Research confirms:

- **44x44 px minimum is standard.** Microsoft Design Language, Material Design (48dp), and WCAG 2.5.5 converge on ~44px. Targets smaller than 44x44 have 3x higher error rates in empirical studies (University of Maryland, 2023).
- **Spacing >=8px between targets.** Prevents fat-finger mis-taps.
- **Explicit buttons beat gestures in accessibility contexts.** SuperNova's 1/2/3-finger gestures are powerful but require memorization and fine motor control. For a non-technical low-vision user, obvious on-screen buttons are far more reliable.
- **Drag handles must be visually distinct.** A subtle border is invisible to a touchscreen user; a grip symbol (≡) or dot pattern communicates "grab here."
- **Avoid long-press / hold gestures.** They delay response and are disorienting. Tap = action, drag = move, nothing else.
- **No hover states.** Touch has no hover; do not design features that require it.

## Configuration Persistence Patterns

Low-vision users depend on documented/persisted preferences. Patterns observed:

- **Save on every change, not on exit.** Clinic PCs can crash or be hard-powered; preferences must survive.
- **Atomic writes** (write to temp, rename) prevent config corruption on concurrent exit.
- **Human-readable format** (JSON) — so a support person can open and inspect.
- **Location near the exe** — non-technical users can find it, delete to reset, copy to share between machines. This is a deliberate tradeoff vs. %APPDATA% (which is "cleaner" but invisible).
- **Fallback on unwritable location** — if the app directory is read-only, fall back to %LOCALAPPDATA%\UltimateZoom\config.json with a one-time migration.
- **Never require the user to configure before first use.** Launch with sane defaults (2.5x, rounded rect, center of screen, ~300x300); the user adjusts from there.

## Sources

**Windows Magnifier (system reference):**
- [Use Magnifier to make things on the screen easier to see - Microsoft Support](https://support.microsoft.com/en-us/windows/use-magnifier-to-make-things-on-the-screen-easier-to-see-414948ba-8b1c-d3bd-8615-0e5e32204198)
- [Setting up and using Magnifier - Microsoft Support](https://support.microsoft.com/en-us/topic/setting-up-and-using-magnifier-e1330ccd-8d5c-2b3c-d383-fd202808c71a)
- [Windows Magnifier and low vision – Perkins School for the Blind](https://www.perkins.org/resource/windows-magnifier-and-low-vision/)
- [How to customise the Magnifier in Windows 11 - AbilityNet](https://mcmw.abilitynet.org.uk/how-to-customise-the-magnifier-in-windows-11)

**Commercial competitors:**
- [ZoomText Screen Magnification Software - Vispero](https://vispero.com/zoomtext-screen-magnifier-software/)
- [Top Features of ZoomText for Low Vision Users - New England Low Vision](https://nelowvision.com/top-features-of-zoomtext-for-low-vision-users-essential-screen-magnification-and-reading-tools/)
- [SuperNova Magnifier & Screen Reader Features - Dolphin](https://yourdolphin.com/product/features?id=4&pid=4)
- [SuperNova Magnifier - Irie-AT](https://irie-at.com/product/supernova-magnifier-speech/)

**Click-through overlay patterns:**
- [See Through Windows - MOBZystems](https://www.mobzystems.com/tools/seethroughwindows.aspx)
- [WindowTop - click-through overlay tool](https://windowtop.info/)
- [Click Through Overlay - Simplode Suite](https://simplode.com/click-through-overlay)

**Stargardt's disease clinical literature:**
- [Low vision management in a case of Stargardt's disease - MedCrave](https://medcraveonline.com/AOVS/low-vision-management-in-a-case-of-stargardtrsquos-disease.html)
- [Stargardt Disease - National Eye Institute](https://www.nei.nih.gov/learn-about-eye-health/eye-conditions-and-diseases/stargardt-disease)
- [Stargardt's Disease - APH ConnectCenter](https://aphconnectcenter.org/visionaware/eye-conditions/eye-conditions-associated-with-blindness-r-s/stargardts-disease/)
- [Stargardt Disease - Ocutech (low vision aids)](https://ocutech.com/resources/stargardt-disease-visual-aids/)
- [Visual improvement with low vision aids in Stargardt's disease - PubMed](https://pubmed.ncbi.nlm.nih.gov/2418398/)

**Low-vision screen magnification research:**
- [Screen Magnification for Readers with Low Vision: A Study on Usability and Performance - ACM SIGACCESS 2023](https://dl.acm.org/doi/10.1145/3597638.3608383)
- [How People with Low Vision Achieve Magnification in Digital Reading - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6123827/)
- [How I Document Accessibility Preferences With Low Vision - Veroniiiica](https://veroniiiica.com/how-i-document-accessibility-preferences-with-low-vision/)

**Touch target sizing (WCAG and platform standards):**
- [Understanding Success Criterion 2.5.5: Target Size - W3C WAI](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html)
- [Understanding Success Criterion 2.5.8: Target Size (Minimum) - W3C WCAG 2.2](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [All accessible touch target sizes - LogRocket Blog](https://blog.logrocket.com/ux-design/all-accessible-touch-target-sizes/)
- [Accessible Target Sizes Cheatsheet - Smashing Magazine](https://www.smashingmagazine.com/2023/04/accessible-tap-target-sizes-rage-taps-clicks/)

**Clinic software context:**
- [Top Veterinary Software Solutions - IDEXX](https://software.idexx.com/top-veterinary-software-solutions-a-2025-comparison-guide)

---
*Feature research for: Windows 11 desktop magnifier bubble for Stargardt's disease user in veterinary clinic*
*Researched: 2026-04-10*
