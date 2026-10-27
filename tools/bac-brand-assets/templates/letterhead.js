// SPDX-License-Identifier: MIT
// Build a CubeSat letterhead v1r1 – A4, English and German. python marks.py && node letterhead.js
//
// Ops surface (Identity Guide §7): white paper, a monochrome hierarchy, no decoration beyond the
// brand's own marks – the logo, and the kicker (the short BAC Yellow dash) before a mono eyebrow.
// Figures, dates and references are IBM Plex Mono; prose is Nunito Sans. Spacing on the 4 px grid
// (1 px = 15 DXA at 96 dpi, so 4 px = 60 DXA).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Header, Footer, Table, TableRow, TableCell,
  WidthType, TableLayoutType, AlignmentType, BorderStyle, PageNumber, VerticalAlign, LineRuleType,
} = require("docx");

const MM = 56.7; // DXA per mm
const PX = 15; // DXA per CSS px
const GRID = (n) => n * 4 * PX; // n grid units
const BODY = "Nunito Sans";
const MONO = "IBM Plex Mono";
const TEXT = "3F3F3F", STRONG = "1F1F1F", MUTED = "6D6D6D", RULE = "D0D0D0";

const marks = JSON.parse(fs.readFileSync("marks.json", "utf8"));
const logo = fs.readFileSync("logo-black.png");
const kickerPng = fs.readFileSync("kicker.png");
// Logo at 40 mm wide; the height follows the PNG's own aspect, never a constant.
const LOGO_W_PX = Math.round(40 / 25.4 * 96);
const LOGO_H_PX = LOGO_W_PX * marks.logo.height / marks.logo.width; // docx-js rounds in EMU, not px

const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideHorizontal: noBorder, insideVertical: noBorder };

// Runs. Sizes are half-points: body 10.5 pt, mono 8 pt (the guide's --text-xs in print).
const body = (text, extra = {}) => new TextRun({ text, font: BODY, size: 21, color: TEXT, ...extra });
const mono = (text, extra = {}) => new TextRun({ text, font: MONO, size: 16, color: MUTED, characterSpacing: 5, ...extra }); // 0.03 em at 8 pt ≈ 5 DXA
const label = (text) => mono(text.toUpperCase(), { color: MUTED });

const L = {
  en: {
    file: "bac-letterhead-en-v1r1.docx", title: "Build a CubeSat letterhead v1r1 (English)",
    address: ["c/o nihil.space GmbH", "Egghölzlistrasse 20", "3006 Bern, Switzerland"],
    recipient: ["Recipient name", "Organisation", "Street and number", "0000 City"],
    meta: [["Date", "Bern, 2026-10-27"], ["Reference", "BAC-2026-001"], ["Contact", "hello@buildacubesat.space"]],
    eyebrow: "OFFER · DEV KIT V1",
    subject: "Subject line in one sentence",
    salutation: "Dear name,",
    paragraphs: [
      "Open with the reason for writing in a single sentence. State what happened, what is needed, or what is being confirmed, so the reader knows the purpose before the second paragraph.",
      "Use the middle of the letter for detail: dates, part numbers, quantities, delivery windows. Keep one idea per paragraph and spell out anything the reader would otherwise have to look up.",
      "Close with the next step and who owns it. Name a date where one applies.",
    ],
    closing: "Kind regards,", sender: "Sender name", role: "Role, Build a CubeSat",
    page: "Page ", of: " of ",
  },
  de: {
    file: "bac-letterhead-de-v1r1.docx", title: "Build a CubeSat Briefpapier v1r1 (Deutsch)",
    address: ["c/o nihil.space GmbH", "Egghölzlistrasse 20", "3006 Bern, Schweiz"],
    recipient: ["Name der Empfängerin oder des Empfängers", "Organisation", "Strasse und Nummer", "0000 Ort"],
    meta: [["Datum", "Bern, 2026-10-27"], ["Referenz", "BAC-2026-001"], ["Kontakt", "hello@buildacubesat.space"]],
    eyebrow: "OFFERTE · DEV KIT V1",
    subject: "Betreff in einem Satz",
    salutation: "Guten Tag",
    paragraphs: [
      "Der erste Satz nennt den Grund des Schreibens: was geschehen ist, was gebraucht wird oder was bestätigt wird. So kennt die Leserin den Zweck, bevor der zweite Absatz beginnt.",
      "Der Mittelteil trägt die Einzelheiten: Daten, Teilenummern, Stückzahlen, Lieferfenster. Ein Gedanke pro Absatz; alles ausschreiben, was sonst nachgeschlagen werden müsste.",
      "Der Schluss nennt den nächsten Schritt und wer ihn verantwortet, mit Datum, wo eines gilt.",
    ],
    closing: "Freundliche Grüsse", sender: "Name", role: "Funktion, Build a CubeSat",
    page: "Seite ", von: " von ", of: " von ",
  },
};

const cellOpts = (w) => ({ width: { size: w, type: WidthType.DXA }, borders: noBorders, verticalAlign: VerticalAlign.TOP, margins: { top: 0, bottom: 0, left: 0, right: 0 } });
const line = (children, extra = {}) => new Paragraph({ spacing: { before: 0, after: 0, line: 276, lineRule: LineRuleType.AUTO }, ...extra, children });

function build(lang) {
  const t = L[lang];
  const contentWidth = 170 * MM; // 210 − 2 × 20

  // Header: the logo left, the address right in mono – the sender's name in strong ink.
  const header = new Header({
    children: [new Table({
      width: { size: contentWidth, type: WidthType.DXA }, columnWidths: [100 * MM, 70 * MM], borders: noBorders, layout: TableLayoutType.FIXED,
      rows: [new TableRow({ children: [
        new TableCell({ ...cellOpts(100 * MM), children: [line([new ImageRun({
          type: "png", data: logo, transformation: { width: LOGO_W_PX, height: LOGO_H_PX },
          altText: { title: "Build a CubeSat", description: "Build a CubeSat logo", name: "bac-logo" },
        })])] }),
        new TableCell({ ...cellOpts(70 * MM), children: [
          line([mono("Build a CubeSat", { color: STRONG })], { alignment: AlignmentType.RIGHT }),
          ...t.address.map((a) => line([mono(a)], { alignment: AlignmentType.RIGHT })),
        ] }),
      ] })],
    })],
  });

  // Footer: a hairline, then the contact line and the page count in mono.
  const footerLines = [["hello@buildacubesat.space", "buildacubesat.space", "+41 31 561 93 45"].join(" · "), "UID CHE-172.893.875"];
  const pageRun = (children) => new TextRun({ font: MONO, size: 16, color: MUTED, children });
  const footer = new Footer({
    children: [
      new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 1 } }, spacing: { after: GRID(2) }, children: [mono("", { size: 4 })] }),
      new Table({
        width: { size: contentWidth, type: WidthType.DXA }, columnWidths: [146 * MM, 24 * MM], borders: noBorders, layout: TableLayoutType.FIXED,
        rows: [new TableRow({ children: [
          new TableCell({ ...cellOpts(146 * MM), children: footerLines.map((f) => line([mono(f)])) }),
          new TableCell({ ...cellOpts(24 * MM), children: [line([mono(t.page), pageRun([PageNumber.CURRENT]), mono(t.of), pageRun([PageNumber.TOTAL_PAGES])], { alignment: AlignmentType.RIGHT })] }),
        ] })],
      }),
    ],
  });

  // The date and reference block: a small mono table, labels muted, values in strong ink.
  const metaTable = new Table({
    width: { size: 80 * MM, type: WidthType.DXA }, columnWidths: [22 * MM, 58 * MM], borders: noBorders, layout: TableLayoutType.FIXED,
    rows: t.meta.map(([k, v]) => new TableRow({ children: [
      new TableCell({ ...cellOpts(22 * MM), children: [line([label(k)], { spacing: { after: GRID(1) } })] }),
      new TableCell({ ...cellOpts(58 * MM), children: [line([mono(v, { color: STRONG, size: 17 })], { spacing: { after: GRID(1) } })] }),
    ] })),
  });

  // The kicker and eyebrow, then the subject as a heading (Nunito Sans 500, 14 pt).
  const kicker = line([
    new ImageRun({ type: "png", data: kickerPng, transformation: { width: 18, height: 4 }, altText: { title: "", description: "", name: "kicker" } }),
    mono("  " + t.eyebrow, { color: STRONG, bold: true }),
  ], { spacing: { before: GRID(8), after: GRID(1) } });
  const subject = line([body(t.subject, { size: 28, color: STRONG })], { spacing: { after: GRID(5) } });

  const para = (text, extra = {}) => line([body(text)], { spacing: { after: GRID(3), line: 300, lineRule: LineRuleType.AUTO }, ...extra });

  const children = [
    ...t.recipient.map((r, i) => line([body(r, i === 0 ? { color: STRONG } : {})])),
    line([body("")], { spacing: { after: GRID(6) } }),
    metaTable,
    kicker,
    subject,
    para(t.salutation),
    ...t.paragraphs.map((p) => para(p)),
    para(t.closing, { spacing: { before: GRID(2), after: GRID(8) } }),
    line([body(t.sender, { color: STRONG })]),
    line([mono(t.role.toUpperCase())]),
  ];

  const doc = new Document({
    creator: "nihil.space GmbH", title: t.title, description: "Build a CubeSat letterhead v1r1. The logo is a BAC Mark of nihil.space GmbH (BAC Trademark Policy).",
    styles: { default: { document: { run: { font: BODY, size: 21, color: TEXT } } } },
    sections: [{
      properties: { page: {
        size: { width: 210 * MM, height: 297 * MM },
        margin: { top: 48 * MM, bottom: 28 * MM, left: 20 * MM, right: 20 * MM, header: 14 * MM, footer: 12 * MM },
      } },
      headers: { default: header },
      footers: { default: footer },
      children,
    }],
  });
  return Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(t.file, buf); console.log("wrote", t.file); });
}

Promise.all([build("en"), build("de")]);
