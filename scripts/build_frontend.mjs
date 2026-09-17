import { build, transform } from 'esbuild';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const DIST = join(ROOT, 'static', 'dist');
const WATCH = process.argv.includes('--watch');

mkdirSync(DIST, { recursive: true });

const cssEntries = [
  'static/css/app.entry.css',
];

// Global-script entries (NOT bundled - they rely on window globals; esbuild
// tree-shakes them as side-effect-free imports). Minified individually so the
// script loading order and global side effects stay intact.
const jsEntries = {
  'categories.js': 'static/js/categories.js',
  'translations.js': 'static/js/translations.js',
  'book-i18n.js': 'static/js/book-i18n.js',
  'cover.js': 'static/js/cover.js',
  'base.js': 'static/js/base.js',
  'index.js': 'static/js/index.js',
};

function hashName(file) {
  return basename(file.path).replace(/\\/g, '/');
}

function simpleHash(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(16);
}

async function buildOnce() {
  const manifest = {};

  // 1. CSS bundle (5 -> 1 minified, hash)
  const css = await build({
    entryPoints: cssEntries.map((p) => join(ROOT, p)),
    outdir: DIST,
    bundle: true,
    minify: true,
    sourcemap: false,
    entryNames: 'app.[hash].min',
    write: false,
  });
  const cssName = hashName(css.outputFiles[0]);
  writeFileSync(join(DIST, cssName), css.outputFiles[0].contents);
  manifest['app.css'] = cssName;
  writeFileSync(join(DIST, 'app.min.css'), css.outputFiles[0].contents);

  // 2. JS: minify each global script individually (keep globals, keep order)
  for (const [key, rel] of Object.entries(jsEntries)) {
    const source = readFileSync(join(ROOT, rel), 'utf-8');
    const out = await transform(source, {
      minify: true,
      loader: 'js',
      target: 'es2020',
    });
    const base = rel.split('/').pop().replace(/\.js$/, '');
    const hash = simpleHash(out.code).slice(0, 8);
    const name = `${base}.${hash}.min.js`;
    writeFileSync(join(DIST, name), out.code);
    manifest[key] = name;
    writeFileSync(join(DIST, `${base}.min.js`), out.code);
  }

  writeFileSync(join(DIST, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(
    '[build-frontend] wrote:',
    Object.values(manifest).join(', '),
    '| stable dev names kept',
  );
}

function cleanup() {
  if (!existsSync(DIST)) return;
  // ponytail: manifest is source of truth; old hashed bundles not in manifest get purged.
  // Stable *.min.js names come from jsEntries so a new entry cannot be written then deleted.
  let keep = new Set(['manifest.json', 'app.min.css']);
  for (const key of Object.keys(jsEntries)) {
    keep.add(key.replace(/\.js$/, '.min.js'));
  }
  try {
    const manifest = JSON.parse(readFileSync(join(DIST, 'manifest.json'), 'utf-8'));
    for (const name of Object.values(manifest)) keep.add(name);
  } catch {
    // no manifest yet: fall back to keeping current prefix files (first build)
  }
  for (const f of readdirSync(DIST)) {
    if (keep.has(f)) continue;
    rmSync(join(DIST, f), { force: true });
  }
}

async function main() {
  if (WATCH) {
    console.log('[build-frontend] watch mode (initial build)');
    await buildOnce();
    return;
  }
  // cleanup 必须在 buildOnce 之后：manifest 是 keep 的依据，构建前它还指向上一轮的
  // 指纹文件名，此时清理会把上一轮产物当成"在用文件"保留下来，于是 dist 每轮多留
  // 一份旧哈希（正好慢一代）。构建后 manifest 已指向新哈希，旧哈希才会被正确清掉。
  await buildOnce();
  cleanup();
}

main().catch((e) => {
  console.error('[build-frontend] FAILED:', e);
  process.exit(1);
});
