// SPDX-License-Identifier: MIT
// Build a CubeSat slides template v1r1 – 16:9, layouts in the master, one sample slide per layout.
// node slides.js && python theme.py bac-slides-template-v1r1.pptx   (marks.py first, for the PNGs)
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
const MUTED = "6D6D6D", BORDER = "E6E6E6", BORDER_STRONG = "D0D0D0", SUNKEN = "F1F1F1";
const INK = "171320", SPACE_MUTED = "8F879E", TEAL_ON_DARK = "1A9A99", ROSE_ON_DARK = "DE5C8C";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 × 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "nihil.space GmbH";
pres.company = "Build a CubeSat";
pres.title = "Build a CubeSat slides template v1r1";
pres.subject = "Build a CubeSat slides template v1r1. The marks are BAC Marks of nihil.space GmbH (BAC Trademark Policy).";
const C = pres.SchemeColor;

const W = 10, H = 5.625, M = 0.5; // margin
const logoBlack = "image/png;base64," + fs.readFileSync("logo-black.png").toString("base64");
const logoWhite = "image/png;base64," + fs.readFileSync("logo-white.png").toString("base64");
const symbolBlack = "image/png;base64," + fs.readFileSync("symbol-black.png").toString("base64");
const symbolWhite = "image/png;base64," + fs.readFileSync("symbol-white.png").toString("base64");
const LOGO_RATIO = 1397 / 650, SYMBOL_RATIO = 400 / 650;

// ---- the shared pieces of every layout -------------------------------------------------
// Footer: deck name (mono, muted) left, the symbol and the slide number right. No bars.
function footer(dark) {
  const color = dark ? SPACE_MUTED : MUTED;
  return [
    { text: { text: "BUILD A CUBESAT · DECK NAME · 2026", options: { x: M, y: H - 0.42, w: 6, h: 0.25, fontFace: MONO, fontSize: 8, color, charSpacing: 1, margin: 0, valign: "middle" } } },
    { image: { data: dark ? symbolWhite : symbolBlack, x: W - M - 0.62, y: H - 0.44, w: 0.28 * SYMBOL_RATIO, h: 0.28 } },
    { placeholder: { options: { name: "slidenum", type: "slide_number" }, text: "" } },
  ];
}
// Eyebrow: the yellow kicker bar before an uppercase mono label (Identity Guide §4.1).
function eyebrow(y, dark) {
  return [
    { rect: { x: M, y: y + 0.06, w: 0.06, h: 0.14, fill: { color: THEME.colors.accent1 } } },
    { placeholder: { options: { name: "eyebrow", type: "body", x: M + 0.14, y, w: 6, h: 0.26, fontFace: MONO, fontSize: 9, color: dark ? SPACE_MUTED : MUTED, charSpacing: 1, margin: 0, valign: "middle" }, text: "· EYEBROW" } },
  ];
}
const title = (y, h, size, color) => ({ placeholder: { options: { name: "title", type: "title", x: M, y, w: W - 2 * M, h, fontSize: size, bold: false, color, align: "left", margin: 0, valign: "top", charSpacing: -0.5 }, text: "Title" } });

const slideNumberOpts = (dark) => ({ x: W - M - 0.3, y: H - 0.42, w: 0.3, h: 0.25, fontFace: MONO, fontSize: 8, color: dark ? SPACE_MUTED : MUTED, align: "right", margin: 0, valign: "middle" });

function define(name, dark, objects, bodyMargin) {
  // the slide number placeholder is positioned through slideNumber, the rest through objects
  pres.defineSlideMaster({
    title: name,
    background: { color: dark ? INK : THEME.colors.lt1 },
    margin: bodyMargin || [0.3, M, 0.7, M],
    objects: objects.filter((o) => !(o.placeholder && o.placeholder.options.type === "slide_number")),
    slideNumber: slideNumberOpts(dark),
  });
}

const BODY_TOP = 1.45, BODY_H = H - BODY_TOP - 0.65;

// 1 Title (light) and 2 Title (Mission, dark)
for (const dark of [false, true]) {
  define(dark ? "TITLE_MISSION" : "TITLE", dark, [
    { image: { data: dark ? logoWhite : logoBlack, x: M, y: M, w: 0.9 * LOGO_RATIO, h: 0.9 } },
    ...eyebrow(2.3, dark),
    title(2.62, 1.1, 40, dark ? C.background1 : C.text1),
    { placeholder: { options: { name: "subtitle", type: "body", x: M, y: 3.75, w: 7, h: 0.8, fontSize: 16, color: dark ? SPACE_MUTED : C.text2, margin: 0, valign: "top" }, text: "Subtitle" } },
    { placeholder: { options: { name: "meta", type: "body", x: M, y: H - 0.42, w: 6, h: 0.25, fontFace: MONO, fontSize: 8, color: dark ? SPACE_MUTED : MUTED, charSpacing: 1, margin: 0, valign: "middle" }, text: "AUTHOR · 2026-10-27" } },
  ]);
}

// 3 Section (light) and 4 Section (Mission, dark)
for (const dark of [false, true]) {
  define(dark ? "SECTION_MISSION" : "SECTION", dark, [
    ...eyebrow(2.05, dark),
    title(2.38, 1.2, 36, dark ? C.background1 : C.text1),
    ...footer(dark),
  ]);
}

// 5 Title and body
define("TITLE_BODY", false, [
  ...eyebrow(0.45, false),
  title(0.78, 0.6, 26, C.text1),
  { placeholder: { options: { name: "body", type: "body", x: M, y: BODY_TOP, w: W - 2 * M, h: BODY_H, fontSize: 14, color: C.text2, margin: 0, valign: "top", paraSpaceAfter: 6 }, text: "Body" } },
  ...footer(false),
]);

// 6 Two columns
define("TWO_COLUMNS", false, [
  ...eyebrow(0.45, false),
  title(0.78, 0.6, 26, C.text1),
  { placeholder: { options: { name: "left", type: "body", x: M, y: BODY_TOP, w: 4.3, h: BODY_H, fontSize: 14, color: C.text2, margin: 0, valign: "top", paraSpaceAfter: 6 }, text: "Left column" } },
  { placeholder: { options: { name: "right", type: "body", x: 5.2, y: BODY_TOP, w: 4.3, h: BODY_H, fontSize: 14, color: C.text2, margin: 0, valign: "top", paraSpaceAfter: 6 }, text: "Right column" } },
  ...footer(false),
]);

// 7 Image and caption: text left, picture right
define("IMAGE_CAPTION", false, [
  ...eyebrow(0.45, false),
  title(0.78, 0.6, 26, C.text1),
  { placeholder: { options: { name: "body", type: "body", x: M, y: BODY_TOP, w: 3.9, h: BODY_H, fontSize: 14, color: C.text2, margin: 0, valign: "top", paraSpaceAfter: 6 }, text: "Caption or commentary" } },
  { placeholder: { options: { name: "image", type: "pic", x: 4.8, y: BODY_TOP, w: 4.7, h: BODY_H, color: MUTED }, text: "Picture" } },
  ...footer(false),
]);

// 8 Title only – for anything composed on the slide (stats, timelines, cards, charts)
define("TITLE_ONLY", false, [
  ...eyebrow(0.45, false),
  title(0.78, 0.6, 26, C.text1),
  ...footer(false),
]);

// 9 Table
define("TABLE", false, [
  ...eyebrow(0.45, false),
  title(0.78, 0.6, 26, C.text1),
  { placeholder: { options: { name: "table", type: "tbl", x: M, y: BODY_TOP, w: W - 2 * M, h: BODY_H, color: C.text2 }, text: "Table" } },
  ...footer(false),
], [0.3, M, 0.75, M]);

// 10 Quote
define("QUOTE", false, [
  { placeholder: { options: { name: "quote", type: "body", x: M, y: 1.4, w: W - 2 * M, h: 2.2, fontSize: 28, color: C.text1, margin: 0, valign: "middle", charSpacing: -0.5 }, text: "Quote" } },
  { placeholder: { options: { name: "attribution", type: "body", x: M, y: 3.75, w: W - 2 * M, h: 0.4, fontFace: MONO, fontSize: 10, color: MUTED, charSpacing: 1, margin: 0 }, text: "NAME · ROLE" } },
  ...footer(false),
]);

// 11 Contact / closing (Mission, dark)
define("CONTACT", true, [
  { image: { data: logoWhite, x: M, y: M, w: 0.9 * LOGO_RATIO, h: 0.9 } },
  title(2.0, 0.8, 32, C.background1),
  { placeholder: { options: { name: "body", type: "body", x: M, y: 2.9, w: 6, h: 1.8, fontFace: MONO, fontSize: 12, color: C.background1, margin: 0, valign: "top", paraSpaceAfter: 4 }, text: "Contact lines" } },
  { placeholder: { options: { name: "meta", type: "body", x: M, y: H - 0.42, w: 6, h: 0.25, fontFace: MONO, fontSize: 8, color: SPACE_MUTED, charSpacing: 1, margin: 0, valign: "middle" }, text: "SPACE IS FOR EVERYONE" } },
]);

// 12 Blank
define("BLANK", false, [...footer(false)]);

// ---- sample slides, one per layout --------------------------------------------------------
pres.addSection({ title: "Template" });
const add = (masterName) => pres.addSlide({ masterName, sectionTitle: "Template" });
let s;

s = add("TITLE");
s.addText("· DECK TYPE · OCTOBER 2026", { placeholder: "eyebrow" });
s.addText("Deck title in Nunito Sans", { placeholder: "title" });
s.addText("One sentence on what this deck is for and who it is for.", { placeholder: "subtitle" });
s.addText("AUTHOR · 2026-10-27 · V0.1", { placeholder: "meta" });
s.addNotes("Title, light (Ops). Use for internal and technical decks. The eyebrow carries the deck type and date.");

s = add("TITLE_MISSION");
s.addText("· MEDIA KIT · OCTOBER 2026", { placeholder: "eyebrow" });
s.addText("Deck title on the Mission hero", { placeholder: "title" });
s.addText("The dark variant for outward-facing decks: sales, media, launches.", { placeholder: "subtitle" });
s.addText("AUTHOR · 2026-10-27", { placeholder: "meta" });
s.addNotes("Title, Mission (dark). Outward-facing decks only; nebula colours are allowed on this surface.");

s = add("SECTION");
s.addText("· 01 · SECTION", { placeholder: "eyebrow" });
s.addText("Section divider", { placeholder: "title" });

s = add("SECTION_MISSION");
s.addText("· 02 · SECTION", { placeholder: "eyebrow" });
s.addText("Section divider on the Mission surface", { placeholder: "title" });

s = add("TITLE_BODY");
s.addText("· ABOUT", { placeholder: "eyebrow" });
s.addText("Title and body", { placeholder: "title" });
s.addText([
  { text: "Sentence case for titles and prose, one idea per slide.", options: { bullet: true, breakLine: true } },
  { text: "Bullets are plain; no icons in the list, no emoji anywhere.", options: { bullet: true, breakLine: true } },
  { text: "Figures and units in IBM Plex Mono: 100×100×227 mm, 12'059 CHF.", options: { bullet: true, breakLine: true } },
  { text: "Caveats are part of the content – (WIP), TBD, PRELIMINARY – not hidden.", options: { bullet: true } },
], { placeholder: "body" });

s = add("TWO_COLUMNS");
s.addText("· COMPARISON", { placeholder: "eyebrow" });
s.addText("Two columns", { placeholder: "title" });
s.addText([
  { text: "Left", options: { bold: true, color: C.text1, breakLine: true } },
  { text: "Before, option A, the problem, the hardware.", options: { breakLine: true } },
  { text: "Three to five lines per column; the slide carries one comparison.", options: {} },
], { placeholder: "left" });
s.addText([
  { text: "Right", options: { bold: true, color: C.text1, breakLine: true } },
  { text: "After, option B, the proposal, the software.", options: { breakLine: true } },
  { text: "Keep the two columns parallel in structure.", options: {} },
], { placeholder: "right" });

s = add("IMAGE_CAPTION");
s.addText("· HARDWARE", { placeholder: "eyebrow" });
s.addText("Image and caption", { placeholder: "title" });
s.addText([
  { text: "Hardware photography, true to life, no filters (Identity Guide §6).", options: { breakLine: true } },
  { text: "The caption says what the picture shows and why it matters here.", options: {} },
], { placeholder: "body" });
s.addImage({ placeholder: "image", data: symbolBlack, x: 4.8 + (4.7 - BODY_H * SYMBOL_RATIO) / 2, y: BODY_TOP, w: BODY_H * SYMBOL_RATIO, h: BODY_H });

// Stat row on the title-only layout
s = add("TITLE_ONLY");
s.addText("· CHANNEL", { placeholder: "eyebrow" });
s.addText("Stat row", { placeholder: "title" });
const stats = [["6'836", "Subscribers", "YouTube, 2026-10"], ["83 %", "Ages 25–44", "Audience"], ["12", "Boards released", "Open hardware"]];
stats.forEach(([n, label, sub], i) => {
  const x = M + i * 3.0, w = 2.8;
  s.addShape(pres.ShapeType.roundRect, { x, y: BODY_TOP, w, h: 2.2, rectRadius: 0.14, fill: { color: SUNKEN }, line: { color: BORDER, width: 0.75 }, objectName: `Stat ${i + 1}` });
  s.addText(n, { x: x + 0.3, y: BODY_TOP + 0.25, w: w - 0.6, h: 1.0, fontFace: MONO, fontSize: 40, color: C.text1, margin: 0, valign: "middle", isTextBox: true, objectName: `Stat ${i + 1} value` });
  s.addText(label, { x: x + 0.3, y: BODY_TOP + 1.3, w: w - 0.6, h: 0.4, fontSize: 14, color: C.text2, margin: 0, isTextBox: true, objectName: `Stat ${i + 1} label` });
  s.addText(sub.toUpperCase(), { x: x + 0.3, y: BODY_TOP + 1.7, w: w - 0.6, h: 0.3, fontFace: MONO, fontSize: 8, color: MUTED, charSpacing: 1, margin: 0, isTextBox: true, objectName: `Stat ${i + 1} source` });
});
s.addNotes("Stats are composed on the title-only layout: a sunken card (--surface-sunken) with a hairline border, the figure in IBM Plex Mono, the label in Nunito Sans, the source as a mono eyebrow.");

// Timeline on the title-only layout
s = add("TITLE_ONLY");
s.addText("· TIMELINE", { placeholder: "eyebrow" });
s.addText("Timeline", { placeholder: "title" });
const steps = [["2020", "Project start"], ["2024", "YouTube devlog"], ["2025", "First suborbital test"], ["2026", "Development kits on sale"]];
const lineY = BODY_TOP + 0.9, inset = 1.3, span = W - 2 * M - 2 * inset;
s.addShape(pres.ShapeType.line, { x: M + 0.2, y: lineY, w: W - 2 * M - 0.4, h: 0, line: { color: BORDER_STRONG, width: 1 }, objectName: "Timeline line" });
steps.forEach(([year, what], i) => {
  const x = M + inset + i * (span / (steps.length - 1));
  const last = i === steps.length - 1;
  s.addShape(pres.ShapeType.ellipse, { x: x - 0.09, y: lineY - 0.09, w: 0.18, h: 0.18, fill: { color: last ? THEME.colors.accent1 : THEME.colors.lt1 }, line: { color: C.text1, width: 1.25 }, objectName: `Step ${i + 1} mark` });
  s.addText(year, { x: x - 1.2, y: lineY - 0.55, w: 2.4, h: 0.3, fontFace: MONO, fontSize: 10, color: MUTED, charSpacing: 1, align: "center", margin: 0, isTextBox: true, objectName: `Step ${i + 1} year` });
  s.addText(what, { x: x - 1.2, y: lineY + 0.25, w: 2.4, h: 0.6, fontSize: 13, color: C.text2, align: "center", margin: 0, valign: "top", isTextBox: true, objectName: `Step ${i + 1} text` });
});
s.addNotes("Timeline on the title-only layout: a --border-strong line, hollow marks, the current step filled BAC Yellow (the one dominant yellow use on the slide).");

s = add("TABLE");
s.addText("· SPECIFICATIONS", { placeholder: "eyebrow" });
s.addText("Table", { placeholder: "title" });
const head = (t) => ({ text: t, options: { bold: true, color: C.text1, border: [{ type: "none" }, { type: "none" }, { type: "solid", color: BORDER_STRONG, pt: 1 }, { type: "none" }] } });
const cell = (t, mono) => ({ text: t, options: { color: C.text2, fontFace: mono ? MONO : undefined, border: [{ type: "none" }, { type: "none" }, { type: "solid", color: BORDER, pt: 0.5 }, { type: "none" }] } });
s.addTable([
  [head("Parameter"), head("Value"), head("Note")],
  [cell("Form factor"), cell("2U", true), cell("100×100×227 mm")],
  [cell("Bus voltage"), cell("3.3 V / 5 V / 12 V", true), cell("bacBus")],
  [cell("Battery"), cell("2S2P", true), cell("Li-ion, development only")],
  [cell("Mass"), cell("TBD", true), cell("(WIP) – measured on the flight build")],
], { placeholder: "table", x: M, y: BODY_TOP, w: W - 2 * M, autoPageSlideStartY: BODY_TOP, fontSize: 12, rowH: 0.4, colW: [2.6, 2.6, 3.8], margin: [0.05, 0.08, 0.05, 0.08], fill: { color: THEME.colors.lt1 } });
s.addNotes("Tables: a strong header rule, hairline row rules, no outer border and no fills (Identity Guide §5.4). Values in IBM Plex Mono.");

s = add("QUOTE");
s.addText("“Space is for everyone.”", { placeholder: "quote" });
s.addText("BUILD A CUBESAT · IDENTITY GUIDE §0", { placeholder: "attribution" });

s = add("CONTACT");
s.addText("Let's talk", { placeholder: "title" });
s.addText([
  { text: "hello@buildacubesat.space", options: { breakLine: true } },
  { text: "buildacubesat.space", options: { breakLine: true } },
  { text: "+41 31 561 93 45", options: { breakLine: true } },
  { text: "nihil.space GmbH · Egghölzlistrasse 20 · 3006 Bern", options: {} },
], { placeholder: "body" });
s.addText("SPACE IS FOR EVERYONE", { placeholder: "meta" });

s = add("BLANK");
s.addText("Blank layout – for full-bleed images, diagrams and charts composed by hand.", { x: M, y: 2.5, w: W - 2 * M, h: 0.6, fontSize: 14, color: MUTED, align: "center", isTextBox: true, objectName: "Hint" });

(async () => {
  const file = "bac-slides-template-v1r1.pptx";
  await pres.writeFile({ fileName: file });
  fs.writeFileSync("theme.json", JSON.stringify(THEME, null, 2));
  console.log("wrote", file, "– now run: python theme.py", file);
})();
