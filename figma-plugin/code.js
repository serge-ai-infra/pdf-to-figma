"use strict";
// S3 gave this file its import/export skeleton in plain JS, on purpose — "a
// build step would be the only thing standing between now and that number,"
// the ceiling S3 exists to measure. S4 is where there's enough logic to earn
// TypeScript: everything below the S3 section is new.
// ---------------------------------------------------------------------------
// Shared constants (S3)
// ---------------------------------------------------------------------------
// Figma imports SVG as CSS pixels, not as points: a 612x792pt page arrives as
// an 816x1056 frame, because CSS defines one point as 4/3px at 96dpi. Measured,
// not assumed — exporting at dpi/72 produced 2267x2934 against a 1700x2200
// reference, exactly 4/3 too large.
const CSS_PX_PER_INCH = 96;
const PT_PER_INCH = 72;
figma.showUI(__html__, { width: 340, height: 720, themeColors: true });
const say = (text, tone) => {
    figma.ui.postMessage({ type: "status", text, tone });
};
const scaleForDpi = (dpi) => dpi / CSS_PX_PER_INCH;
// ---------------------------------------------------------------------------
// S3: import vector, export raster
// ---------------------------------------------------------------------------
async function importSvg(svg, name) {
    let node;
    try {
        node = figma.createNodeFromSvg(svg);
    }
    catch (err) {
        say("Could not parse that SVG: " + err.message, "error");
        return;
    }
    node.name = name;
    node.x = 0;
    node.y = 0;
    figma.currentPage.appendChild(node);
    figma.currentPage.selection = [node];
    figma.viewport.scrollAndZoomIntoView([node]);
    const ptW = Math.round((node.width * PT_PER_INCH) / CSS_PX_PER_INCH);
    const ptH = Math.round((node.height * PT_PER_INCH) / CSS_PX_PER_INCH);
    say('Imported "' + name + '" — ' +
        Math.round(node.width) + "×" + Math.round(node.height) + "px " +
        "(" + ptW + "×" + ptH + "pt source), " +
        countNodes(node) + " nodes", "ok");
}
function countNodes(node) {
    if (!("children" in node))
        return 1;
    return node.children.reduce((sum, child) => sum + countNodes(child), 1);
}
async function exportPng(dpi) {
    const selection = figma.currentPage.selection;
    if (selection.length !== 1) {
        say("Select exactly one frame to export.", "error");
        return;
    }
    const node = selection[0];
    const scale = scaleForDpi(dpi);
    let bytes;
    try {
        bytes = await node.exportAsync({
            format: "PNG",
            constraint: { type: "SCALE", value: scale },
        });
    }
    catch (err) {
        say("Export failed: " + err.message, "error");
        return;
    }
    const width = Math.round(node.width * scale);
    const height = Math.round(node.height * scale);
    figma.ui.postMessage({
        type: "png",
        bytes,
        name: node.name + "@" + dpi + "dpi.png",
        width,
        height,
    });
    say("Exported " + width + "×" + height + "px at " + dpi + " dpi", "ok");
}
// ---------------------------------------------------------------------------
// S4: build from a payload
//
// Payload/PayloadNode are duplicated from `emitter/src/payload.ts` rather
// than shared, deliberately — the two are independent TypeScript projects
// with different module systems (this file compiles to a single global
// script; the emitter is Node ESM), and the shape is small, stable and
// consumed one-way. Keep the two in sync by hand if either changes.
// ---------------------------------------------------------------------------
const PAYLOAD_VERSION = "0.1";
const COMPONENTS_PAGE_NAME = "Components";
const BUILD_FRAME_NAME = "pdf2figma build";
function hexToRgb(hex) {
    return {
        r: parseInt(hex.slice(1, 3), 16) / 255,
        g: parseInt(hex.slice(3, 5), 16) / 255,
        b: parseInt(hex.slice(5, 7), 16) / 255,
    };
}
/** Best-effort mapping from IR weight/italic to a Figma style name. Good
 * enough for the standard-14 fonts this pass targets; a font whose style
 * names don't follow this convention simply fails to load and gets skipped,
 * not silently substituted. */
function styleFor(weight, italic) {
    const bold = weight !== undefined && weight >= 600;
    if (bold && italic)
        return "Bold Italic";
    if (bold)
        return "Bold";
    if (italic)
        return "Italic";
    return "Regular";
}
async function tryLoadFont(family, weight, italic) {
    const fontName = { family, style: styleFor(weight, italic) };
    try {
        await figma.loadFontAsync(fontName);
        return fontName;
    }
    catch (_a) {
        return null;
    }
}
function sizeForResize(value) {
    // Figma refuses to resize a non-line node to exactly 0 in either axis.
    return Math.max(value, 0.01);
}
/** Always sets fill/stroke explicitly, one way or the other — never leaves
 * either alone when the payload doesn't carry one. A conditional-only-when-
 * truthy version would leave a reused instance wearing a stale stroke it
 * never had (see `applyInstanceStyle` below), so "no value in the payload"
 * has to mean "clear it," not "skip it." */
function applyShapeStyle(node, payloadNode) {
    if ("fills" in node) {
        node.fills = payloadNode.fill ? [{ type: "SOLID", color: hexToRgb(payloadNode.fill) }] : [];
    }
    node.strokes = payloadNode.strokeColor
        ? [{ type: "SOLID", color: hexToRgb(payloadNode.strokeColor) }]
        : [];
    if (payloadNode.strokeColor && payloadNode.strokeWidth !== undefined) {
        node.strokeWeight = payloadNode.strokeWidth;
    }
}
/** A reused master's instance starts out wearing the master's own color —
 * this repaints it with *this* node's raw fill/stroke, the same values
 * `applyShapeStyle`/`createMaster` use for a component's first occurrence.
 * Without this, every instance past the first in a candidateId cluster keeps
 * whatever the first occurrence happened to be painted (see S5 fill/stroke
 * mismatch findings — one-off color reuse across a shape/text cluster is
 * common, e.g. the same icon glyph in four different accent colors). Clears
 * to "no fill"/"no stroke" when the payload doesn't carry one, same reasoning
 * as `applyShapeStyle` — otherwise an instance whose own node has no stroke
 * keeps the master's, in the same cluster where a sibling does have one. */
function applyInstanceStyle(instance, node) {
    const visual = instance.children.length > 0 ? instance.children[0] : instance;
    if (node.kind === "text") {
        if ("fills" in visual) {
            visual.fills = node.fill ? [{ type: "SOLID", color: hexToRgb(node.fill) }] : [];
        }
        return;
    }
    if ("fills" in visual) {
        applyShapeStyle(visual, node);
    }
}
function createPlainShape(node) {
    const shape = node.kind === "rect" ? figma.createRectangle() : node.kind === "ellipse" ? figma.createEllipse() : figma.createLine();
    shape.resize(sizeForResize(node.bbox.w), sizeForResize(node.bbox.h));
    shape.x = node.bbox.x;
    shape.y = node.bbox.y;
    shape.name = node.name;
    applyShapeStyle(shape, node);
    return shape;
}
function ensureComponentsPage() {
    const existing = figma.root.children.find((p) => p.name === COMPONENTS_PAGE_NAME);
    if (existing)
        return existing;
    const page = figma.createPage();
    page.name = COMPONENTS_PAGE_NAME;
    return page;
}
function findBuildFrame() {
    return figma.currentPage.findOne((n) => n.type === "FRAME" && n.name === BUILD_FRAME_NAME);
}
function ensureBuildFrame() {
    const existing = findBuildFrame();
    if (existing) {
        for (const child of [...existing.children])
            child.remove();
        return existing;
    }
    const frame = figma.createFrame();
    frame.name = BUILD_FRAME_NAME;
    figma.currentPage.appendChild(frame);
    return frame;
}
const MASTER_GAP = 40;
/** Masters are laid out left to right so they never land on top of each
 * other — `createComponent()` alone always defaults to (0, 0). */
function nextMasterX(componentsPage) {
    if (componentsPage.children.length === 0)
        return 0;
    const rightEdge = componentsPage.children.reduce((max, child) => Math.max(max, child.x + child.width), 0);
    return rightEdge + MASTER_GAP;
}
/** Only reached when creating a master for the first time — see the caller. */
async function createMaster(node, componentsPage) {
    var _a;
    let child;
    if (node.kind === "text") {
        const text = figma.createText();
        if (node.font) {
            const font = await tryLoadFont(node.font.family, node.font.weight, node.font.italic);
            if (!font) {
                text.remove();
                return null; // no font, no master — never fake it with a substitute
            }
            text.fontName = font;
            text.fontSize = node.font.size;
        }
        text.characters = node.name;
        if (node.fill)
            text.fills = [{ type: "SOLID", color: hexToRgb(node.fill) }];
        child = text;
    }
    else {
        child = createPlainShape(node);
    }
    child.x = 0;
    child.y = 0;
    const offsetX = nextMasterX(componentsPage);
    const master = figma.createComponent();
    master.resize(sizeForResize(node.bbox.w), sizeForResize(node.bbox.h));
    master.appendChild(child);
    master.name = node.name;
    master.setPluginData("candidateId", (_a = node.candidateId) !== null && _a !== void 0 ? _a : "");
    componentsPage.appendChild(master);
    master.x = offsetX;
    master.y = 0;
    return master;
}
async function buildComponentInstance(node, componentsPage, counts) {
    var _a;
    const candidateId = node.candidateId;
    if (candidateId === null)
        return null;
    let master = componentsPage.findOne((n) => n.type === "COMPONENT" && n.getPluginData("candidateId") === candidateId);
    if (!master) {
        master = await createMaster(node, componentsPage);
        if (!master)
            return null;
        counts.mastersCreated++;
    }
    else {
        counts.mastersReused++;
    }
    const instance = master.createInstance();
    instance.resize(sizeForResize(node.bbox.w), sizeForResize(node.bbox.h));
    instance.x = node.bbox.x;
    instance.y = node.bbox.y;
    instance.name = node.name;
    instance.setPluginData("sourceNodeId", node.id);
    applyInstanceStyle(instance, node);
    if (node.kind === "text" && node.liveText && node.font) {
        const textChild = instance.findOne((n) => n.type === "TEXT");
        const font = await tryLoadFont(node.font.family, node.font.weight, node.font.italic);
        if (textChild && font) {
            textChild.fontName = font;
            textChild.characters = (_a = node.text) !== null && _a !== void 0 ? _a : "";
        }
    }
    counts.instances++;
    return instance;
}
async function buildPlainNode(node, counts) {
    var _a;
    if (node.kind === "text") {
        const text = figma.createText();
        if (node.font) {
            const font = await tryLoadFont(node.font.family, node.font.weight, node.font.italic);
            if (!font) {
                text.remove();
                return null; // no font, no text node — skipped and reported, not faked
            }
            text.fontName = font;
            text.fontSize = node.font.size;
        }
        text.characters = (_a = node.text) !== null && _a !== void 0 ? _a : "";
        if (node.fill)
            text.fills = [{ type: "SOLID", color: hexToRgb(node.fill) }];
        // A PDF text run is a single line. A fixed width equal to the source bbox
        // makes Figma wrap it the moment the substituted font runs a hair wider,
        // so size to the content first and never go narrower than that.
        text.textAutoResize = "WIDTH_AND_HEIGHT";
        text.resize(Math.max(text.width, sizeForResize(node.bbox.w)), sizeForResize(node.bbox.h));
        text.x = node.bbox.x;
        text.y = node.bbox.y;
        text.name = node.name;
        text.setPluginData("sourceNodeId", node.id);
        counts.plain++;
        return text;
    }
    const shape = createPlainShape(node);
    shape.setPluginData("sourceNodeId", node.id);
    counts.plain++;
    return shape;
}
async function buildFromPayload(payload) {
    if (payload.payload_version !== PAYLOAD_VERSION) {
        say(`Unrecognized payload version ${payload.payload_version} (expected ${PAYLOAD_VERSION})`, "error");
        return;
    }
    await figma.loadAllPagesAsync();
    const componentsPage = ensureComponentsPage();
    const buildFrame = ensureBuildFrame();
    buildFrame.resize(sizeForResize(payload.page.width), sizeForResize(payload.page.height));
    const counts = { mastersCreated: 0, mastersReused: 0, instances: 0, plain: 0, skipped: 0 };
    for (const node of payload.nodes) {
        if (node.kind === "unsupported") {
            counts.skipped++;
            continue;
        }
        const built = node.component && node.candidateId !== null
            ? await buildComponentInstance(node, componentsPage, counts)
            : await buildPlainNode(node, counts);
        if (built) {
            buildFrame.appendChild(built);
        }
        else {
            counts.skipped++;
        }
    }
    figma.currentPage.selection = [buildFrame];
    figma.viewport.scrollAndZoomIntoView([buildFrame]);
    say(`${counts.mastersCreated} master(s) created, ${counts.mastersReused} reused, ` +
        `${counts.instances} instance(s), ${counts.plain} plain node(s), ${counts.skipped} skipped`, "ok");
}
// ---------------------------------------------------------------------------
// S5: export the built tree back into IR-shaped data
//
// The counterpart to S4's payload, in the other direction — the structural
// diff half of verification needs "built IR" and nothing produced that
// before this. BuiltNode/BuiltDocument are duplicated from the Python model
// rather than shared, same reasoning as Payload in S4.
// ---------------------------------------------------------------------------
const BUILT_VERSION = "0.1";
const PT_TO_PX = 4 / 3; // same ratio as emitter/src/payload.ts's PT_TO_PX
function rgbToHex(color) {
    const channel = (v) => Math.round(v * 255).toString(16).padStart(2, "0");
    return "#" + channel(color.r) + channel(color.g) + channel(color.b);
}
function weightItalicFromStyle(style) {
    const lower = style.toLowerCase();
    return {
        weight: lower.includes("bold") ? 700 : undefined,
        italic: lower.includes("italic") || lower.includes("oblique"),
    };
}
function firstSolidFill(node) {
    if (!("fills" in node))
        return undefined;
    const fills = node.fills;
    if (fills === figma.mixed || !Array.isArray(fills))
        return undefined;
    const solid = fills.find((f) => f.type === "SOLID" && f.visible !== false);
    return solid ? rgbToHex(solid.color) : undefined;
}
function firstSolidStroke(node) {
    if (!("strokes" in node) || !Array.isArray(node.strokes))
        return {};
    const solid = node.strokes.find((s) => s.type === "SOLID" && s.visible !== false);
    if (!solid)
        return {};
    const weight = "strokeWeight" in node && typeof node.strokeWeight === "number" ? node.strokeWeight : undefined;
    return { color: rgbToHex(solid.color), weight };
}
/** Every node this plugin's *build* step creates is either the visual node
 * itself (a plain rect/ellipse/line/text) or a one-child instance/component
 * wrapping one — see `createMaster`/`createPlainShape` — so `children[0]`
 * was exactly right there. A donor (`importDonors`, `figma.createNodeFromSvg`)
 * breaks that assumption: its crop is a region of the full-page SVG, and a
 * background path from a neighboring shape (a card, a chart's panel) can
 * geometrically overlap that region and get pulled in as an earlier sibling,
 * painted first. The frame's own declared size is still the donor's true
 * bbox, though — the sibling that actually fits it (unlike an oversized
 * background bleeding in) is the shape the donor was generated for. Falls
 * back to plain `children[0]` when there's only one child, so build-step
 * nodes are unaffected. */
function visualNode(node) {
    if (!("children" in node) || node.children.length === 0)
        return node;
    if (node.children.length === 1)
        return node.children[0];
    const sizeDelta = (child) => Math.abs(child.width - node.width) + Math.abs(child.height - node.height);
    // On a tie, prefer the later child: a progress bar's full-width track and
    // its (here, 100%-filled) value bar can share the exact same rect, and the
    // value bar — the one actually meant to be visible — is painted second.
    return node.children.reduce((best, child) => (sizeDelta(child) <= sizeDelta(best) ? child : best));
}
function exportNode(node) {
    const sourceId = node.getPluginData("sourceNodeId");
    if (!sourceId)
        return null;
    const bbox = {
        x: node.x / PT_TO_PX,
        y: node.y / PT_TO_PX,
        w: node.width / PT_TO_PX,
        h: node.height / PT_TO_PX,
    };
    const visual = visualNode(node);
    const built = { id: sourceId, bbox };
    if (visual.type === "TEXT") {
        built.text = visual.characters;
        built.fill = firstSolidFill(visual);
        const fontName = visual.fontName;
        const fontSize = visual.fontSize;
        if (fontName !== figma.mixed && typeof fontSize === "number") {
            const { weight, italic } = weightItalicFromStyle(fontName.style);
            // Back to points, like the bbox above: the payload painted in px.
            built.font = { family: fontName.family, size: fontSize / PT_TO_PX, weight, italic };
        }
    }
    else {
        built.fill = firstSolidFill(visual);
        const stroke = firstSolidStroke(visual);
        built.strokeColor = stroke.color;
        built.strokeWidth = stroke.weight !== undefined ? stroke.weight / PT_TO_PX : undefined;
    }
    return built;
}
function exportBuiltIR() {
    const buildFrame = findBuildFrame();
    if (!buildFrame) {
        say(`No "${BUILD_FRAME_NAME}" frame on this page — build something first.`, "error");
        return;
    }
    const nodes = [];
    let skipped = 0;
    for (const child of buildFrame.children) {
        const built = exportNode(child);
        if (built) {
            nodes.push(built);
        }
        else {
            skipped++; // untagged — not something this plugin built, e.g. hand-added
        }
    }
    const doc = {
        built_version: BUILT_VERSION,
        page: { width: buildFrame.width / PT_TO_PX, height: buildFrame.height / PT_TO_PX },
        nodes,
    };
    figma.ui.postMessage({ type: "built-ir", json: JSON.stringify(doc, null, 2) });
    say(`Exported ${nodes.length} node(s)` + (skipped ? `, ${skipped} untagged node(s) skipped` : ""), "ok");
}
// ---------------------------------------------------------------------------
// S3.5: import geometry donors — cropped, geometry-only SVG for a `path`-kind
// shape (`emitter/src/payload.ts` marks every one `unsupported`, permanently
// — no raw contour survives S1's classification). Numbered after S5 here
// because it was built after S4/S5 existed, same "everything below is new"
// convention this file's own header comment already uses; the roadmap slot
// (between S3 and S4) is a pipeline position, not a file-order requirement.
//
// The only integration point is `sourceNodeId` — `exportNode` above already
// walks every tagged child of the build frame generically, so a donor node
// becomes verifiable with zero changes to `payload.ts`, `verify/model.py`,
// or `structural.py`. See docs/specs/s3.5-geometry-donor/spec.md.
// ---------------------------------------------------------------------------
const CONVERT_VERSION = "0.1";
async function importDonors(donors) {
    if (donors.convert_version !== CONVERT_VERSION) {
        say(`Unrecognized donor version ${donors.convert_version} (expected ${CONVERT_VERSION})`, "error");
        return;
    }
    const buildFrame = findBuildFrame();
    if (!buildFrame) {
        say(`No "${BUILD_FRAME_NAME}" frame on this page — build something first.`, "error");
        return;
    }
    let imported = 0;
    let skipped = 0;
    // Every donor goes in *behind* whatever Build already placed — never
    // appended (topmost). A donor is typically a background/decorative path
    // (a card panel, a donut, a section-header strip) that the source PDF
    // paints early (low z), with text and other shapes painted over it
    // afterward. `verify structural` doesn't catch this: it compares each
    // tagged node's own properties, not what's drawn in front of it — a
    // donor silently burying a `liveText` label underneath it still reports
    // `matched` for both. `insertChild(0, ...)` is confirmed by the plugin
    // typings to mean bottom-most paint order, not array-index-zero-as-
    // "first created"; inserting each donor at an increasing index (rather
    // than always 0) keeps their own relative order intact while the entire
    // batch stays below every pre-existing child.
    let insertAt = 0;
    for (const donor of donors.nodes) {
        let node;
        try {
            node = figma.createNodeFromSvg(donor.svg);
        }
        catch (err) {
            say(`Skipped ${donor.id}: ${err.message}`, "error");
            skipped++;
            continue;
        }
        // Re-importing the same id replaces, not duplicates — the same
        // idempotency `buildComponentInstance`'s master lookup already gives
        // every other node kind. Without this, clicking the panel twice (or two
        // overlapping donor sets) leaves two nodes tagged with one sourceNodeId;
        // `verify structural`'s built-by-id map would then silently keep only
        // one, hiding the duplicate instead of reporting it as `extra`.
        const previous = buildFrame.findOne((n) => n.getPluginData("sourceNodeId") === donor.id);
        previous === null || previous === void 0 ? void 0 : previous.remove();
        // Explicit, not trusted from the SVG's own declared size — the same
        // defensiveness every other node this plugin builds already gets.
        node.resize(sizeForResize(donor.bbox.w * PT_TO_PX), sizeForResize(donor.bbox.h * PT_TO_PX));
        node.x = donor.bbox.x * PT_TO_PX;
        node.y = donor.bbox.y * PT_TO_PX;
        node.name = donor.id;
        node.setPluginData("sourceNodeId", donor.id);
        buildFrame.insertChild(insertAt, node);
        insertAt++;
        imported++;
    }
    figma.currentPage.selection = [buildFrame];
    figma.viewport.scrollAndZoomIntoView([buildFrame]);
    say(`${imported} donor(s) imported` + (skipped ? `, ${skipped} skipped` : ""), "ok");
}
// ---------------------------------------------------------------------------
figma.ui.onmessage = async (msg) => {
    if (msg.type === "import-svg" && msg.svg && msg.name) {
        await importSvg(msg.svg, msg.name);
    }
    else if (msg.type === "export-png" && msg.dpi) {
        await exportPng(msg.dpi);
    }
    else if (msg.type === "build-payload" && msg.payload) {
        await buildFromPayload(msg.payload);
    }
    else if (msg.type === "export-built-ir") {
        exportBuiltIR();
    }
    else if (msg.type === "import-donors" && msg.donors) {
        await importDonors(msg.donors);
    }
    else if (msg.type === "close") {
        figma.closePlugin();
    }
};
