// Re-exports the raster icons from icon.svg, icon-app.svg and icon-maskable.svg.
// Needs the `sharp` package (it renders SVG with librsvg). Nothing is downloaded:
// run it with an existing install on NODE_PATH, for example from the web app:
//   NODE_PATH=web/node_modules node design/icons/export-icons.cjs
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const sharp = require("sharp");

const dir = __dirname;

// Render an SVG to a square PNG of `size` pixels.
async function render(svgFile, size) {
  const svg = fs.readFileSync(path.join(dir, svgFile));
  const { width } = await sharp(svg).metadata(); // SVG user units at 72 dpi
  return sharp(svg, { density: (72 * size) / width })
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toBuffer();
}

// Pack PNG images into one .ico file (PNG-compressed entries).
function ico(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(images.length, 4);
  let offset = 6 + 16 * images.length;
  const entries = images.map(({ size, png }) => {
    const e = Buffer.alloc(16);
    e.writeUInt8(size >= 256 ? 0 : size, 0); // width
    e.writeUInt8(size >= 256 ? 0 : size, 1); // height
    e.writeUInt8(0, 2); // no palette
    e.writeUInt8(0, 3); // reserved
    e.writeUInt16LE(1, 4); // colour planes
    e.writeUInt16LE(32, 6); // bits per pixel
    e.writeUInt32LE(png.length, 8);
    e.writeUInt32LE(offset, 12);
    offset += png.length;
    return e;
  });
  return Buffer.concat([header, ...entries, ...images.map((i) => i.png)]);
}

async function main() {
  const icoSizes = [16, 32, 48];
  const icoImages = [];
  for (const size of icoSizes) icoImages.push({ size, png: await render("icon.svg", size) });
  fs.writeFileSync(path.join(dir, "favicon.ico"), ico(icoImages));

  const pngs = [
    ["icon-app.svg", 192, "icon-192.png"],
    ["icon-app.svg", 512, "icon-512.png"],
    ["icon-maskable.svg", 512, "icon-maskable-512.png"],
    ["icon-maskable.svg", 180, "apple-touch-icon.png"],
  ];
  for (const [src, size, out] of pngs) {
    let img = sharp(await render(src, size));
    // The Apple touch icon must have no transparency.
    if (out === "apple-touch-icon.png") img = img.flatten({ background: "#EDF2EF" }).removeAlpha();
    await img.png({ compressionLevel: 9 }).toFile(path.join(dir, out));
  }
  console.log("Wrote favicon.ico, icon-192.png, icon-512.png, icon-maskable-512.png, apple-touch-icon.png");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
