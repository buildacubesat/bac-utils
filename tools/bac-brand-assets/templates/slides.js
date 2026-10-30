// SPDX-License-Identifier: MIT
// Build a CubeSat slides template v1r2 – 16:9, layouts in the master, one sample slide per layout.
// python marks.py && python surfaces.py && node slides.js && python theme.py bac-slides-template-v1r2.pptx
// nebula.jpg (1920 × 1080) is a source file kept beside this script.
//
// The language comes from the BAC Reference Gallery (document family, Dev Kit product sheet), the
// Tooldance media kit (2026-10) and the Identity Guide §3–§7. Slides are a presentation surface, so
// Mission: the light layouts sit on the warm --space-paper with paper wells that carry a teal, violet
// or rose top rule; the dark layouts sit on the nebula (nebula.jpg) and carry Plasma Rose for
// non-semantic emphasis. The kicker – a short BAC Yellow dash before a strong mono eyebrow – is the
// brand mark that opens every slide; figures are IBM Plex Mono; display type is Nunito Sans 500 with
// tight tracking.
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const THEME = {
  name: "Build a CubeSat",
  headFontFace: "Nunito Sans",
  bodyFontFace: "Nunito Sans",
  colors: {
    dk1: "1F1F1F", lt1: "FFFFFF", dk2: "3F3F3F", lt2: "F9F9F9",
    accent1: "F7D400", accent2: "004C8B", accent3: "0E9594", accent4: "7A5AF8", accent5: "C64677", accent6: "3FB950",
    hlink: "0B5CAD", folHlink: "0B5CAD",
  },
};
const MONO = "IBM Plex Mono";
// Identity Guide §4 – neutrals and the Mission set, literal values.
const STRONG = "1F1F1F", TEXT = "3F3F3F", MUTED = "6D6D6D", FAINT = "8A8A8A";
const BORDER_STRONG = "D0D0D0";
const YELLOW = "F7D400", BLUE = "004C8B", RED = "E94538";
const INK = "171320", PAPER = "F4F1EA", SPACE_MUTED = "8F879E", SPACE_FAINT = "3B3350";
const ROSE_ON_DARK = "DE5C8C", TEAL_ON_DARK = "1A9A99", VIOLET_ON_DARK = "8F73FF";
// The nebula triad: fills for marks and rules, inks for text on paper (Identity Guide §4.2).
const TEAL = "0E9594", VIOLET = "7A5AF8", ROSE = "C64677";
const TEAL_INK = "007878", VIOLET_INK = "6E4BE8", ROSE_INK = "B8396B";
// Mission paper well (§7, surface 2) flattened for pptx: white 42 % over paper, edge rgba(36,27,63,.14).
const WELL = "F9F7F4", WELL_EDGE = "D7D3D2", PAPER_FAINT = "DDD7CB";
// The viewport's panel colour, for dark cards on the nebula.
const VIEWPORT_INK = "101421";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 × 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "nihil.space GmbH";
pres.company = "Build a CubeSat";
pres.title = "Build a CubeSat slides template v1r2";
pres.subject = "Build a CubeSat slides template v1r2. The marks are BAC Marks of nihil.space GmbH (BAC Trademark Policy).";

const W = 10, H = 5.625, M = 0.5;
const png = (f) => "image/png;base64," + fs.readFileSync(f).toString("base64");
const marks = JSON.parse(fs.readFileSync("marks.json", "utf8"));
const LOGO_RATIO = marks.logo.width / marks.logo.height;
const TAGLINE_RATIO = marks["logo-tagline"].width / marks["logo-tagline"].height;
const SYMBOL_RATIO = marks.symbol.width / marks.symbol.height;
const img = {
  logoBlack: png("logo-black.png"), logoWhite: png("logo-white.png"), taglineWhite: png("logo-tagline-white.png"),
  symbolBlack: png("symbol-black.png"), symbolWhite: png("symbol-white.png"),
  nebula: "image/jpeg;base64," + fs.readFileSync("nebula.jpg").toString("base64"), viewport: png("viewport.png"),
};

// ---- type scale (pt): the guide's rem scale with body 16 pt = 1 rem -----------------------------
const T = { display: 40, section: 44, h1: 32, lead: 18, body: 16, small: 14, quote: 36, figure: 56, eyebrow: 10, label: 9, micro: 8 };
const TRACK_TIGHT = (pt) => -0.02 * pt; // --ls-tight
const TRACK_LABEL = (pt) => 0.03 * pt; // --ls-label – tight, not spaced-out
const mono = (pt, color, extra = {}) => ({ fontFace: MONO, fontSize: pt, color, charSpacing: TRACK_LABEL(pt), margin: 0, ...extra });

// ---- the shared pieces -----------------------------------------------------------------------
// Kicker: the short BAC Yellow dash (18 × 4 px in the gallery, rounded) before a strong, uppercase mono
// eyebrow. The dash is the brand mark; the eyebrow is a placeholder so every slide names its context.
function kicker(y, dark, w = 6) {
  const pt = T.eyebrow, lineH = 0.3;
  return [
    { rect: { x: M, y: y + lineH / 2 - 0.025, w: 0.2, h: 0.05, rectRadius: 0.025, fill: { color: YELLOW }, line: { color: YELLOW, width: 0 } } },
    { placeholder: { options: { name: "eyebrow", type: "body", x: M + 0.3, y, w, h: lineH, ...mono(pt, dark ? ROSE_ON_DARK : STRONG, { bold: true, valign: "middle" }) }, text: "EYEBROW" } },
  ];
}
// Display and heading placeholders: Nunito Sans 500, tight tracking, sentence case.
const heading = (name, y, h, size, color, w = W - 2 * M, extra = {}) => ({
  placeholder: { options: { name, type: name === "title" ? "title" : "body", x: M, y, w, h, fontSize: size, bold: false, color, align: "left", margin: 0, valign: "top", charSpacing: TRACK_TIGHT(size), lineSpacingMultiple: 1.05, ...extra }, text: "Title" },
});
const bodyPh = (name, x, y, w, h, extra = {}) => ({
  placeholder: { options: { name, type: "body", x, y, w, h, fontSize: T.body, color: TEXT, margin: 0, valign: "top", paraSpaceAfter: 8, lineSpacingMultiple: 1.2, ...extra }, text: "Body" },
});
// Footer: deck name (mono, muted) left, the symbol and the slide number right. No bars.
function footer(dark, rightEdge = W - M) {
  const color = dark ? SPACE_MUTED : MUTED;
  return [
    { text: { text: "BUILD A CUBESAT · DECK NAME · 2026", options: { x: M, y: H - 0.42, w: 5, h: 0.25, ...mono(T.micro, color, { valign: "middle" }) } } },
    { image: { data: dark ? img.symbolWhite : img.symbolBlack, x: rightEdge - 0.62, y: H - 0.45, w: 0.3 * SYMBOL_RATIO, h: 0.3 } },
  ];
}
const slideNumberOpts = (dark, rightEdge = W - M) => ({ x: rightEdge - 0.3, y: H - 0.42, w: 0.3, h: 0.25, ...mono(T.micro, dark ? SPACE_MUTED : MUTED, { align: "right", valign: "middle" }) });

// A paper well with an optional nebula top rule – the card of the light layouts.
function well(x, y, w, h, accent) {
  const out = [{ rect: { x, y, w, h, rectRadius: 0.1, fill: { color: WELL }, line: { color: WELL_EDGE, width: 0.75 } } }];
  if (accent) out.push({ rect: { x: x + 0.12, y, w: w - 0.24, h: 0.05, fill: { color: accent }, line: { color: accent, width: 0 } } });
  return out;
}

function define(name, dark, objects, opts = {}) {
  pres.defineSlideMaster({
    title: name,
    background: dark ? { data: img.nebula } : { color: PAPER },
    margin: [0.3, M, 0.7, M],
    objects,
    slideNumber: opts.noNumber ? undefined : slideNumberOpts(dark, opts.rightEdge),
  });
}

const BODY_TOP = 1.55, BODY_H = H - BODY_TOP - 0.7;
const contentHead = (dark = false) => [...kicker(0.45, dark), heading("title", 0.78, 0.7, T.h1, dark ? PAPER : STRONG)];

// 1 TITLE – light, on paper, with a half-bleed photo slot on the right (hardware photography, §6).
define("TITLE", false, [
  { placeholder: { options: { name: "image", type: "pic", x: 5.6, y: 0, w: 4.4, h: H, color: FAINT }, text: "Hardware photo" } },
  { image: { data: img.logoBlack, x: M, y: M, w: 0.8 * LOGO_RATIO, h: 0.8 } },
  ...kicker(1.75, false, 4.6),
  heading("title", 2.1, 2.0, 40, STRONG, 4.8),
  bodyPh("subtitle", M, 4.3, 4.6, 0.6, { fontSize: T.lead, color: TEXT, lineSpacingMultiple: 1.2 }),
  { placeholder: { options: { name: "meta", type: "body", x: M, y: H - 0.42, w: 4.6, h: 0.25, ...mono(T.micro, MUTED, { valign: "middle" }) }, text: "AUTHOR · 2026-10-27" } },
], { noNumber: true });

// 2 TITLE_MISSION – the nebula with the recessed viewport (Identity Guide §7, surface 1).
const VP = { x: 5.75, y: 0.95, w: 3.75, h: 2.8125 }; // 4:3, the viewport.png aspect
define("TITLE_MISSION", true, [
  { image: { data: img.viewport, ...VP } },
  { placeholder: { options: { name: "image", type: "pic", x: VP.x + 0.2, y: VP.y + 0.2, w: VP.w - 0.4, h: VP.h - 0.55, color: SPACE_MUTED }, text: "Product image" } },
  { text: { text: "PRODUCT IMAGE · 4:3", options: { x: VP.x + 0.25, y: VP.y + VP.h - 0.33, w: VP.w - 0.5, h: 0.2, ...mono(T.micro, TEAL_ON_DARK, { align: "right", valign: "middle" }) } } },
  { image: { data: img.logoWhite, x: M, y: M, w: 0.8 * LOGO_RATIO, h: 0.8 } },
  ...kicker(1.75, true, 4.6),
  heading("title", 2.1, 2.0, 40, PAPER, 4.9),
  bodyPh("subtitle", M, 4.3, 4.8, 0.6, { fontSize: T.lead, color: SPACE_MUTED, lineSpacingMultiple: 1.2 }),
  { placeholder: { options: { name: "meta", type: "body", x: M, y: H - 0.42, w: 4.6, h: 0.25, ...mono(T.micro, SPACE_MUTED, { valign: "middle" }) }, text: "AUTHOR · 2026-10-27" } },
], { noNumber: true });

// 3 SECTION and 4 SECTION_MISSION – a faint display numeral in mono, the section title under it.
for (const dark of [false, true]) {
  define(dark ? "SECTION_MISSION" : "SECTION", dark, [
    ...kicker(1.0, dark),
    { placeholder: { options: { name: "number", type: "body", x: M, y: 1.35, w: 6, h: 1.4, fontFace: MONO, fontSize: 88, color: dark ? SPACE_FAINT : PAPER_FAINT, margin: 0, valign: "top", lineSpacingMultiple: 1.0 }, text: "01" } },
    heading("title", 3.0, 1.4, T.section, dark ? PAPER : STRONG, 8),
    ...footer(dark),
  ]);
}

// 5 TITLE_BODY
define("TITLE_BODY", false, [...contentHead(), bodyPh("body", M, BODY_TOP, W - 2 * M, BODY_H), ...footer(false)]);

// 6 TWO_COLUMNS – two paper wells, teal and violet top rules
const COL_W = 4.4, COL_H = BODY_H - 0.1;
define("TWO_COLUMNS", false, [
  ...contentHead(),
  ...well(M, BODY_TOP, COL_W, COL_H, TEAL),
  ...well(W - M - COL_W, BODY_TOP, COL_W, COL_H, VIOLET),
  bodyPh("left", M + 0.3, BODY_TOP + 0.3, COL_W - 0.6, COL_H - 0.5, { fontSize: T.small }),
  bodyPh("right", W - M - COL_W + 0.3, BODY_TOP + 0.3, COL_W - 0.6, COL_H - 0.5, { fontSize: T.small }),
  ...footer(false),
]);

// 7 IMAGE_CAPTION – text left; the picture right in a paper well with a mono caption.
const FR = { x: 5.0, y: 0.85, w: 4.5, h: 3.65 };
define("IMAGE_CAPTION", false, [
  ...kicker(0.45, false, 4),
  heading("title", 0.78, 1.1, T.h1, STRONG, 4.1),
  bodyPh("body", M, 2.0, 4.1, 2.5, { fontSize: T.small }),
  ...well(FR.x, FR.y, FR.w, FR.h),
  { placeholder: { options: { name: "image", type: "pic", x: FR.x + 0.15, y: FR.y + 0.15, w: FR.w - 0.3, h: FR.h - 0.3, color: FAINT }, text: "Picture" } },
  { placeholder: { options: { name: "caption", type: "body", x: FR.x, y: FR.y + FR.h + 0.08, w: FR.w, h: 0.25, ...mono(T.label, MUTED, { align: "right", valign: "top" }) }, text: "FIG. 01 · WHAT THE PICTURE SHOWS" } },
  ...footer(false),
]);

// 8 TITLE_ONLY – for anything composed on the slide (stats, the hero card, timelines, charts)
define("TITLE_ONLY", false, [...contentHead(), ...footer(false)]);

// 8b TITLE_ONLY_MISSION – the same on the nebula: timelines, roadmaps, one big statement
define("TITLE_ONLY_MISSION", true, [...contentHead(true), ...footer(true)]);

// 9 TABLE
define("TABLE", false, [
  ...contentHead(),
  { placeholder: { options: { name: "table", type: "tbl", x: M, y: BODY_TOP, w: W - 2 * M, h: BODY_H, color: TEXT }, text: "Table" } },
  ...footer(false),
]);

// 10 QUOTE – one claim per slide: a Plasma Rose opening mark (decorative, §4.5), the quote, a portrait
// and name block, and a half-bleed photo slot on the right like the title slide.
const QW = 5.2;
define("QUOTE", false, [
  { placeholder: { options: { name: "image", type: "pic", x: 6.0, y: 0, w: 4.0, h: H, color: FAINT }, text: "Photo" } },
  { text: { text: "\u201C", options: { x: M - 0.06, y: 0.25, w: 1.4, h: 1.5, fontSize: 140, color: ROSE, margin: 0, valign: "top" } } },
  { placeholder: { options: { name: "quote", type: "body", x: M, y: 1.45, w: QW, h: 2.2, fontSize: 30, color: STRONG, margin: 0, valign: "top", charSpacing: TRACK_TIGHT(30), lineSpacingMultiple: 1.1 }, text: "Quote" } },
  { rect: { x: M, y: 3.85, w: 0.5, h: 0.05, fill: { color: ROSE }, line: { color: ROSE, width: 0 } } },
  { placeholder: { options: { name: "portrait", type: "pic", x: M, y: 4.08, w: 0.62, h: 0.62, color: FAINT }, text: "Portrait" } },
  { placeholder: { options: { name: "name", type: "body", x: M + 0.8, y: 4.1, w: QW - 0.8, h: 0.3, fontSize: T.small, color: STRONG, margin: 0, valign: "middle" }, text: "Name" } },
  { placeholder: { options: { name: "attribution", type: "body", x: M + 0.8, y: 4.42, w: QW - 0.8, h: 0.26, ...mono(T.label, MUTED, { valign: "middle" }) }, text: "ROLE · ORGANIZATION" } },
], { noNumber: true });

// 11 CONTACT – Mission closing; the tagline lockup carries SPACE FOR EVERYONE (§8), never a free line.
define("CONTACT", true, [
  { image: { data: img.taglineWhite, x: M, y: M, w: 0.9 * TAGLINE_RATIO, h: 0.9 } },
  heading("title", 2.0, 0.9, T.section, PAPER, 6),
  bodyPh("body", M, 3.05, 6, 1.6, { fontFace: MONO, fontSize: 13, color: PAPER, paraSpaceAfter: 4, lineSpacingMultiple: 1.25 }),
  { placeholder: { options: { name: "meta", type: "body", x: M, y: H - 0.42, w: 6, h: 0.25, ...mono(T.micro, SPACE_MUTED, { valign: "middle" }) }, text: "DECK NAME · 2026-10-27" } },
], { noNumber: true });

// 12 BLANK
define("BLANK", false, [...footer(false)]);

// ---- sample slides, one per layout --------------------------------------------------------
pres.addSection({ title: "Template" });
const add = (masterName) => pres.addSlide({ masterName, sectionTitle: "Template" });
let s;

s = add("TITLE");
s.addText("DECK TYPE · OCTOBER 2026", { placeholder: "eyebrow" });
s.addText("Open hardware, built to be understood.", { placeholder: "title" });
s.addText("One sentence on what this deck is for and who it is for.", { placeholder: "subtitle" });
s.addText("AUTHOR · 2026-10-27 · V0.1", { placeholder: "meta" });
s.addImage({ placeholder: "image", data: png("sample-led-board.png"), x: 5.6, y: 0, w: 4.4, h: H, sizing: { type: "cover", w: 4.4, h: H } });
s.addNotes("Title on paper: internal and technical decks. The right half is a photo slot – real hardware, true to life, no filters (Identity Guide §6). Delete the slot for a text-only title.");

s = add("TITLE_MISSION");
s.addText("MEDIA KIT · OCTOBER 2026", { placeholder: "eyebrow" });
s.addText("Space for everyone.", { placeholder: "title" });
s.addText("The Mission variant for outward-facing decks: sales, media, launches.", { placeholder: "subtitle" });
s.addText("AUTHOR · 2026-10-27", { placeholder: "meta" });
s.addImage({ placeholder: "image", data: png("sample-cubesat-wireframe.png"), x: VP.x + 0.2, y: VP.y + 0.2, w: VP.w - 0.4, h: VP.h - 0.55, sizing: { type: "contain", w: VP.w - 0.4, h: VP.h - 0.55 } });
s.addNotes("Title on the nebula: outward-facing decks. The eyebrow takes Plasma Rose, the kicker stays BAC Yellow. The viewport on the right is the product-render slot; a photo or a CAD-derived outline both belong there.");

s = add("SECTION");
s.addText("SECTION", { placeholder: "eyebrow" });
s.addText("01", { placeholder: "number" });
s.addText("Section divider", { placeholder: "title" });

s = add("SECTION_MISSION");
s.addText("SECTION", { placeholder: "eyebrow" });
s.addText("02", { placeholder: "number" });
s.addText("Section divider on the Mission surface", { placeholder: "title" });

s = add("TITLE_BODY");
s.addText("ABOUT", { placeholder: "eyebrow" });
s.addText("Title and body", { placeholder: "title" });
s.addText([
  { text: "Sentence case for titles and prose, one idea per slide.", options: { bullet: true, breakLine: true } },
  { text: "Bullets are plain; no icons in the list, no emoji anywhere.", options: { bullet: true, breakLine: true } },
  { text: "Figures and units in IBM Plex Mono – 100×100×227 mm, 12'059 CHF – so columns line up.", options: { bullet: true, breakLine: true } },
  { text: "Caveats are part of the content – (WIP), TBD, PRELIMINARY – not hidden.", options: { bullet: true } },
], { placeholder: "body" });

s = add("TWO_COLUMNS");
s.addText("COMPARISON", { placeholder: "eyebrow" });
s.addText("Two columns", { placeholder: "title" });
s.addText([
  { text: "LEFT", options: { ...mono(T.label, MUTED), bold: true, breakLine: true } },
  { text: "Before, option A, the problem, the hardware.", options: { breakLine: true } },
  { text: "Three to five lines per column; the slide carries one comparison.", options: {} },
], { placeholder: "left" });
s.addText([
  { text: "RIGHT", options: { ...mono(T.label, MUTED), bold: true, breakLine: true } },
  { text: "After, option B, the proposal, the software.", options: { breakLine: true } },
  { text: "Keep the two columns parallel in structure.", options: {} },
], { placeholder: "right" });

s = add("IMAGE_CAPTION");
s.addText("HARDWARE", { placeholder: "eyebrow" });
s.addText("Image and caption", { placeholder: "title" });
s.addText([
  { text: "Hardware photography, true to life, no filters (Identity Guide §6).", options: { breakLine: true } },
  { text: "The caption says what the picture shows and why it matters here.", options: {} },
], { placeholder: "body" });
s.addImage({ placeholder: "image", data: png("sample-led-board.png"), x: FR.x + 0.15, y: FR.y + 0.15, w: FR.w - 0.3, h: FR.h - 0.3, sizing: { type: "contain", w: FR.w - 0.3, h: FR.h - 0.3 } });
s.addText("FIG. 01 · EPS MAIN BOARD, BENCH BUILD", { placeholder: "caption" });

// Stat row with the hero card on the title-only layout
s = add("TITLE_ONLY");
s.addText("CHANNEL", { placeholder: "eyebrow" });
s.addText("Key figures", { placeholder: "title" });
// The hero card (Identity Guide §6): one per view, info blue, white text, uppercase title over the short red rule.
const HC = { x: M, y: BODY_TOP, w: 3.3, h: 2.5 };
s.addShape(pres.ShapeType.roundRect, { ...HC, rectRadius: 0.1, fill: { color: BLUE }, line: { color: BLUE, width: 0 }, objectName: "Hero card" });
s.addText("NEXT MILESTONE", { x: HC.x + 0.3, y: HC.y + 0.3, w: HC.w - 0.6, h: 0.35, fontSize: 16, color: "FFFFFF", margin: 0, valign: "middle", isTextBox: true, objectName: "Hero card title" });
s.addShape(pres.ShapeType.rect, { x: HC.x + 0.3, y: HC.y + 0.72, w: 0.4, h: 0.03, fill: { color: RED }, line: { color: RED, width: 0 }, objectName: "Hero card rule" });
s.addText("2027-Q1", { x: HC.x + 0.3, y: HC.y + 0.9, w: HC.w - 0.6, h: 0.9, fontFace: MONO, fontSize: 44, color: "FFFFFF", margin: 0, valign: "middle", isTextBox: true, objectName: "Hero card figure" });
s.addText("Dev Kit v1 ships", { x: HC.x + 0.3, y: HC.y + 1.85, w: HC.w - 0.6, h: 0.3, fontSize: T.small, color: "FFFFFF", margin: 0, isTextBox: true, objectName: "Hero card label" });
const stats = [["6'836", "Subscribers", "YouTube · 2026-10"], ["83\u202f%", "Ages 25–44", "Audience"], ["12", "Boards released", "Open hardware"], ["2U", "Form factor", "Dev Kit v1"]];
stats.forEach(([n, label, sub], i) => {
  const col = i % 2, row = Math.floor(i / 2), w = 2.75, h = 1.17;
  const x = HC.x + HC.w + 0.25 + col * (w + 0.2), y = BODY_TOP + row * (h + 0.16);
  const accent = [TEAL, VIOLET, ROSE, TEAL][i];
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.1, fill: { color: WELL }, line: { color: WELL_EDGE, width: 0.75 }, objectName: `Stat ${i + 1}` });
  s.addShape(pres.ShapeType.rect, { x: x + 0.12, y, w: w - 0.24, h: 0.05, fill: { color: accent }, line: { color: accent, width: 0 }, objectName: `Stat ${i + 1} rule` });
  s.addText(sub.toUpperCase(), { x: x + 0.25, y: y + 0.15, w: w - 0.5, h: 0.22, ...mono(T.label, MUTED, { valign: "middle" }), isTextBox: true, objectName: `Stat ${i + 1} source` });
  s.addText(n, { x: x + 0.25, y: y + 0.38, w: w - 0.5, h: 0.5, fontFace: MONO, fontSize: 30, color: STRONG, margin: 0, valign: "middle", isTextBox: true, objectName: `Stat ${i + 1} value` });
  s.addText(label, { x: x + 0.25, y: y + 0.86, w: w - 0.5, h: 0.25, fontSize: T.small, color: TEXT, margin: 0, isTextBox: true, objectName: `Stat ${i + 1} label` });
});
s.addNotes("Composed on the title-only layout. One hero card per deck lifts the single most important item (info blue, white text, the short red rule is decorative – Identity Guide §6). Stats are paper wells with a nebula top rule: mono source label, mono figure, sans label.");

// Timeline on the nebula: done steps in Orbital Teal, the current one BAC Yellow, the next hollow;
// a mono date over each node, a title and a line of description under it, a callout card below.
s = add("TITLE_ONLY_MISSION");
s.addText("TIMELINE", { placeholder: "eyebrow" });
s.addText("From a bench project to a kit on sale", { placeholder: "title" });
const steps = [
  ["2020", "Project start", "Build a CubeSat begins"],
  ["2024", "YouTube devlog", "Every design step in public"],
  ["2025", "Suborbital test", "First flight of BAC hardware"],
  ["2026-12", "Dev Kit v1 orders", "2U development kit, open hardware"],
  ["2027-01", "Dev Kit v1 ships", "First kits leave Bern"],
];
const NOW = 3;
const tlX0 = M + 0.85, tlX1 = W - M - 0.85, tlY = BODY_TOP + 0.75, gap = (tlX1 - tlX0) / (steps.length - 1);
steps.forEach((_, i) => {
  if (i === steps.length - 1) return;
  const done = i < NOW;
  s.addShape(pres.ShapeType.line, { x: tlX0 + i * gap, y: tlY, w: gap, h: 0, line: { color: done ? TEAL : SPACE_MUTED, width: done ? 2 : 1, dashType: done ? "solid" : "dash" }, objectName: `Timeline segment ${i + 1}` });
});
steps.forEach(([date, title, text], i) => {
  const x = tlX0 + i * gap, done = i < NOW, now = i === NOW;
  const r = now ? 0.13 : 0.1;
  s.addShape(pres.ShapeType.ellipse, { x: x - r, y: tlY - r, w: 2 * r, h: 2 * r, fill: done || now ? { color: now ? YELLOW : TEAL } : { color: INK }, line: { color: now ? YELLOW : done ? TEAL : SPACE_MUTED, width: 1.5 }, objectName: `Step ${i + 1} mark` });
  s.addText(date, { x: x - 0.85, y: tlY - 0.5, w: 1.7, h: 0.25, ...mono(T.label, now ? YELLOW : TEAL_ON_DARK, { bold: true, align: "center", valign: "bottom" }), isTextBox: true, objectName: `Step ${i + 1} date` });
  s.addText(title, { x: x - 0.85, y: tlY + 0.24, w: 1.7, h: 0.3, fontSize: 13, color: PAPER, align: "center", margin: 0, valign: "top", isTextBox: true, objectName: `Step ${i + 1} title` });
  s.addText(text, { x: x - 0.8, y: tlY + 0.56, w: 1.6, h: 0.55, fontSize: 10, color: SPACE_MUTED, align: "center", margin: 0, valign: "top", isTextBox: true, objectName: `Step ${i + 1} text` });
});
const CB = { x: M, y: BODY_TOP + 2.2, w: W - 2 * M, h: 0.85 };
s.addShape(pres.ShapeType.roundRect, { ...CB, rectRadius: 0.1, fill: { color: VIEWPORT_INK, transparency: 25 }, line: { color: TEAL, width: 1, transparency: 45 }, objectName: "Callout" });
s.addText("NEXT", { x: CB.x + 0.3, y: CB.y + 0.15, w: 2, h: 0.22, ...mono(T.label, ROSE_ON_DARK, { bold: true, valign: "middle" }), isTextBox: true, objectName: "Callout label" });
s.addText("Dev Kit v1 orders open in December; shipping early January 2027.", { x: CB.x + 0.3, y: CB.y + 0.4, w: CB.w - 0.6, h: 0.32, fontSize: T.small, color: PAPER, margin: 0, valign: "middle", isTextBox: true, objectName: "Callout text" });
s.addNotes("Timeline on the nebula (TITLE_ONLY_MISSION). Done steps in Orbital Teal with a solid line, the current step BAC Yellow (the slide's one yellow besides the kicker), the steps ahead hollow on a dashed line. Dates in mono. The callout is a viewport-ink card with a teal edge and a Plasma Rose label. Up to five steps fit.");

s = add("TABLE");
s.addText("SPECIFICATIONS", { placeholder: "eyebrow" });
s.addText("Table", { placeholder: "title" });
const head = (t) => ({ text: t.toUpperCase(), options: { ...mono(T.label, MUTED), bold: true, border: [{ type: "none" }, { type: "none" }, { type: "solid", color: STRONG, pt: 1 }, { type: "none" }] } });
const cell = (t, isMono) => ({ text: t, options: { color: TEXT, fontSize: T.small, fontFace: isMono ? MONO : undefined, border: [{ type: "none" }, { type: "none" }, { type: "solid", color: WELL_EDGE, pt: 0.5 }, { type: "none" }] } });
s.addTable([
  [head("Parameter"), head("Value"), head("Note")],
  [cell("Form factor"), cell("2U", true), cell("100×100×227 mm")],
  [cell("Bus voltage"), cell("3.3 V / 5 V / 12 V", true), cell("bacBus")],
  [cell("Battery"), cell("2S2P", true), cell("Li-ion, development only")],
  [cell("Mass"), cell("TBD", true), cell("(WIP) – measured on the flight build")],
], { placeholder: "table", x: M, y: BODY_TOP, w: W - 2 * M, autoPageSlideStartY: BODY_TOP, rowH: 0.42, colW: [2.6, 2.6, 3.8], margin: [0.06, 0.08, 0.06, 0.08], fill: { color: PAPER }, valign: "middle" });
s.addNotes("Tables: a strong header rule, hairline row rules, no outer border and no fills (Identity Guide §5.4). Header labels in mono uppercase, values in IBM Plex Mono.");

s = add("QUOTE");
s.addText("Engineering should be understandable.", { placeholder: "quote" });
s.addImage({ placeholder: "portrait", data: img.symbolBlack, x: M + 0.12, y: 4.08, w: 0.62 * SYMBOL_RATIO, h: 0.62 });
s.addText("Build a CubeSat", { placeholder: "name" });
s.addText("IDENTITY GUIDE · §2 VOICE & TONE", { placeholder: "attribution" });
s.addImage({ placeholder: "image", data: png("sample-led-board.png"), x: 6.0, y: 0, w: 4.0, h: H, sizing: { type: "cover", w: 4.0, h: H } });
s.addNotes("Quote: one sentence, the speaker's portrait (a square photo, cropped round by the frame) with name and role, and a photo of what they talk about on the right. Delete the photo slot for a quote that stands alone; the quote box then takes the full width.");

s = add("CONTACT");
s.addText("Let's talk", { placeholder: "title" });
s.addText([
  { text: "hello@buildacubesat.space", options: { breakLine: true } },
  { text: "buildacubesat.space", options: { breakLine: true } },
  { text: "+41 31 561 93 45", options: { breakLine: true } },
  { text: "nihil.space GmbH · Egghölzlistrasse 20 · 3006 Bern", options: { color: SPACE_MUTED } },
], { placeholder: "body" });
s.addText("MEDIA KIT · 2026-10-27", { placeholder: "meta" });
const RC = { x: 6.35, y: 1.25, w: 3.15, h: 3.2 };
s.addShape(pres.ShapeType.roundRect, { ...RC, rectRadius: 0.1, fill: { color: VIEWPORT_INK, transparency: 25 }, line: { color: TEAL, width: 1, transparency: 45 }, objectName: "Resources card" });
s.addText("RESOURCES", { x: RC.x + 0.25, y: RC.y + 0.2, w: RC.w - 0.5, h: 0.22, ...mono(T.label, ROSE_ON_DARK, { bold: true, valign: "middle" }), isTextBox: true, objectName: "Resources label" });
[["Documentation", "docs.buildacubesat.space"], ["Hardware", "bac.page/hardware"], ["YouTube", "youtube.com/@buildacubesat"]].forEach(([k, v], i) => {
  const y = RC.y + 0.6 + i * 0.82;
  s.addText(k, { x: RC.x + 0.25, y, w: RC.w - 0.5, h: 0.3, fontSize: 13, color: PAPER, margin: 0, valign: "middle", isTextBox: true, objectName: `Resource ${i + 1}` });
  s.addText(v, { x: RC.x + 0.25, y: y + 0.3, w: RC.w - 0.5, h: 0.25, ...mono(T.label, TEAL_ON_DARK, { valign: "middle" }), isTextBox: true, objectName: `Resource ${i + 1} link` });
});

s = add("BLANK");
s.addText("Blank layout – for full-bleed images, diagrams and charts composed by hand.", { x: M, y: 2.5, w: W - 2 * M, h: 0.6, fontSize: T.small, color: MUTED, align: "center", isTextBox: true, objectName: "Hint" });

(async () => {
  const file = "bac-slides-template-v1r2.pptx";
  await pres.writeFile({ fileName: file });
  fs.writeFileSync("theme.json", JSON.stringify(THEME, null, 2));
  console.log("wrote", file, "– now run: python theme.py", file);
})();
