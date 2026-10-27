// SPDX-License-Identifier: MIT
// Build a CubeSat letterhead v1r1 – A4, English and German. node letterhead.js
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Header, Footer, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, TabStopType, PageNumber, VerticalAlign, LineRuleType,
} = require("docx");

const MM = 56.7; // DXA per mm
const BODY = "Nunito Sans";
const MONO = "IBM Plex Mono";
const TEXT = "3F3F3F", STRONG = "1F1F1F", MUTED = "6D6D6D", RULE = "D0D0D0";

const logo = fs.readFileSync("logo-black.png");

const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideHorizontal: noBorder, insideVertical: noBorder };

const mono = (text, extra = {}) => new TextRun({ text, font: MONO, size: 14, color: MUTED, ...extra }); // 7.5 pt
const body = (text, extra = {}) => new TextRun({ text, font: BODY, size: 21, color: TEXT, ...extra }); // 10.5 pt

const L = {
  en: {
    file: "bac-letterhead-en-v1r1.docx", title: "Build a CubeSat letterhead v1r1 (English)",
    address: ["c/o nihil.space GmbH", "Egghölzlistrasse 20", "3006 Bern, Switzerland"],
    recipient: ["Recipient name", "Organisation", "Street and number", "0000 City"],
    date: "Bern, 2026-10-27",
    subject: "Subject line goes here",
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
    date: "Bern, 2026-10-27",
    subject: "Betreff",
    salutation: "Guten Tag",
    paragraphs: [
      "Der erste Satz nennt den Grund des Schreibens: was geschehen ist, was gebraucht wird oder was bestätigt wird. So kennt die Leserin den Zweck, bevor der zweite Absatz beginnt.",
      "Der Mittelteil trägt die Einzelheiten: Daten, Teilenummern, Stückzahlen, Lieferfenster. Ein Gedanke pro Absatz; alles ausschreiben, was sonst nachgeschlagen werden müsste.",
      "Der Schluss nennt den nächsten Schritt und wer ihn verantwortet, mit Datum, wo eines gilt.",
    ],
    closing: "Freundliche Grüsse", sender: "Name", role: "Funktion, Build a CubeSat",
    page: "Seite ", of: " von ",
  },
};

function build(lang) {
  const t = L[lang];
  const contentWidth = 170 * MM; // 210 − 2 × 20

  const header = new Header({
    children: [
      new Table({
        width: { size: contentWidth, type: WidthType.DXA },
        columnWidths: [100 * MM, 70 * MM],
        borders: noBorders,
        rows: [new TableRow({ children: [
          new TableCell({
            width: { size: 100 * MM, type: WidthType.DXA }, borders: noBorders, verticalAlign: VerticalAlign.TOP,
            margins: { top: 0, bottom: 0, left: 0, right: 0 },
            children: [new Paragraph({ children: [new ImageRun({
              type: "png", data: logo,
              transformation: { width: 151, height: 71 }, // 40 × 18.9 mm at 96 dpi units; logo is 1397 × 650
              altText: { title: "Build a CubeSat", description: "Build a CubeSat logo", name: "bac-logo" },
            })] })],
          }),
          new TableCell({
            width: { size: 70 * MM, type: WidthType.DXA }, borders: noBorders, verticalAlign: VerticalAlign.TOP,
            margins: { top: 0, bottom: 0, left: 0, right: 0 },
            children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { after: 0 }, children: [mono("Build a CubeSat", { color: STRONG })] }),
              ...t.address.map((line) => new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { after: 0 }, children: [mono(line)] }))],
          }),
        ] })],
      }),
    ],
  });

  const footerLine = ["hello@buildacubesat.space", "buildacubesat.space", "+41 31 561 93 45", "UID CHE-172.893.875"].join(" · ");
  const cell = (w, align, runs) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders: noBorders, margins: { top: 0, bottom: 0, left: 0, right: 0 },
    children: [new Paragraph({ style: "BacFooter", alignment: align, spacing: { after: 0 }, children: runs })],
  });
  const footer = new Footer({
    children: [
      new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 1 } }, spacing: { after: 80 }, children: [mono("", { size: 4 })] }),
      new Table({
        width: { size: contentWidth, type: WidthType.DXA }, columnWidths: [142 * MM, 28 * MM], borders: noBorders,
        rows: [new TableRow({ children: [
          cell(142 * MM, AlignmentType.LEFT, [mono(footerLine)]),
          cell(28 * MM, AlignmentType.RIGHT, [mono(t.page), new TextRun({ font: MONO, size: 15, color: MUTED, children: [PageNumber.CURRENT] }), mono(t.of), new TextRun({ font: MONO, size: 15, color: MUTED, children: [PageNumber.TOTAL_PAGES] })]),
        ] })],
      }),
    ],
  });

  const p = (children, extra = {}) => new Paragraph({ spacing: { after: 0, line: 300, lineRule: LineRuleType.AUTO }, ...extra, children });
  const blank = () => p([body("")]);

  const children = [
    ...t.recipient.map((line) => p([body(line)])),
    blank(), blank(),
    p([mono(t.date, { size: 17 })]),
    blank(), blank(),
    p([body(t.subject, { bold: true, color: STRONG })]),
    blank(),
    p([body(t.salutation)]),
    blank(),
  ];
  t.paragraphs.forEach((text) => { children.push(p([body(text)])); children.push(blank()); });
  children.push(p([body(t.closing)]), blank(), blank(), p([body(t.sender)]), p([body(t.role, { color: MUTED })]));

  const doc = new Document({
    creator: "nihil.space GmbH", title: t.title, description: "Build a CubeSat letterhead v1r1. The logo is a BAC Mark of nihil.space GmbH (BAC Trademark Policy).",
    styles: { default: { document: { run: { font: BODY, size: 21, color: TEXT } } },
      paragraphStyles: [{ id: "BacFooter", name: "BAC Footer", basedOn: "Normal", run: { font: MONO, size: 14, color: MUTED } }] },
    sections: [{
      properties: {
        page: {
          size: { width: 210 * MM, height: 297 * MM },
          margin: { top: 50 * MM, bottom: 25 * MM, left: 20 * MM, right: 20 * MM, header: 14 * MM, footer: 12 * MM },
        },
      },
      headers: { default: header },
      footers: { default: footer },
      children,
    }],
  });
  return Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(t.file, buf); console.log("wrote", t.file); });
}

Promise.all([build("en"), build("de")]);
