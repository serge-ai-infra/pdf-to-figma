#!/usr/bin/env node
/**
 * The only file in this package that touches the filesystem — mirrors
 * `src/pdf2figma/cli.py`'s role for the Python side. Everything else takes
 * parsed objects, never a path.
 */

import { readFileSync, writeFileSync } from "node:fs";

import { IR_VERSION } from "./ir.js";
import type { IRDocument } from "./ir.js";
import { INVENTORY_VERSION } from "./inventory.js";
import type { Inventory } from "./inventory.js";
import type { Profile } from "./profile.js";
import { buildPayload } from "./payload.js";

interface Args {
  irPath: string;
  inventoryPath: string;
  profilePath?: string;
  page: number;
  output?: string;
  pretty: boolean;
}

function parseArgs(argv: string[]): Args {
  const positional: string[] = [];
  let profilePath: string | undefined;
  let pageArg: string | undefined;
  let output: string | undefined;
  let pretty = false;

  const takeValue = (flag: string, i: number): string => {
    const value = argv[i];
    if (value === undefined) throw new Error(`${flag} needs a value`);
    return value;
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === undefined) break;
    if (arg === "--profile") {
      profilePath = takeValue(arg, ++i);
    } else if (arg === "--page") {
      pageArg = takeValue(arg, ++i);
    } else if (arg === "-o" || arg === "--output") {
      output = takeValue(arg, ++i);
    } else if (arg === "--pretty") {
      pretty = true;
    } else if (arg.startsWith("-")) {
      throw new Error(`unrecognized flag: ${arg}`);
    } else {
      positional.push(arg);
    }
  }

  const [irPath, inventoryPath] = positional;
  if (!irPath || !inventoryPath) {
    throw new Error(
      "usage: emit <doc.ir.json> <corpus.inventory.json> " +
        "[--profile p.json] [--page N] [-o out.payload.json] [--pretty]",
    );
  }

  const page = pageArg === undefined ? 1 : Number(pageArg);
  if (!Number.isInteger(page) || page < 1) {
    throw new Error(`--page must be a positive integer, got ${pageArg}`);
  }

  return { irPath, inventoryPath, profilePath, page, output, pretty };
}

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

function main(argv: string[]): number {
  let args: Args;
  try {
    args = parseArgs(argv);
  } catch (err) {
    console.error(`error: ${(err as Error).message}`);
    return 1;
  }

  let ir: IRDocument;
  let inventory: Inventory;
  let profile: Profile | undefined;
  try {
    ir = readJson<IRDocument>(args.irPath);
    inventory = readJson<Inventory>(args.inventoryPath);
    profile = args.profilePath ? readJson<Profile>(args.profilePath) : undefined;
  } catch (err) {
    console.error(`error: ${(err as Error).message}`);
    return 1;
  }

  if (ir.ir_version !== IR_VERSION) {
    console.error(`error: ${args.irPath}: IR version ${ir.ir_version} != ${IR_VERSION}`);
    return 2;
  }
  if (inventory.inventory_version !== INVENTORY_VERSION) {
    console.error(
      `error: ${args.inventoryPath}: inventory version ${inventory.inventory_version} != ${INVENTORY_VERSION}`,
    );
    return 2;
  }

  let payload;
  try {
    payload = buildPayload(ir, args.page - 1, inventory, profile);
  } catch (err) {
    console.error(`error: ${(err as Error).message}`);
    return 2;
  }

  const text = JSON.stringify(payload, null, args.pretty ? 2 : undefined);
  const supported = payload.nodes.filter((n) => n.kind !== "unsupported").length;
  const skipped = payload.nodes.length - supported;

  if (args.output) {
    writeFileSync(args.output, text + "\n", "utf8");
    console.error(`${supported} node(s), ${skipped} skipped -> ${args.output}`);
  } else {
    console.log(text);
  }

  return 0;
}

process.exitCode = main(process.argv.slice(2));
