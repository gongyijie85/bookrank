import { build, transform } from 'esbuild';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const DIST = join(ROOT, 'static', 'dist');
const WATCH = process.argv.includes('--watch');

mkdirSync(DIST, { recursive: true });

const cssEntries = [
  'static/css/base.css',
  'static/css/components.css',
  'static/css/animations.css',
  'static/css/index.css',
  'static/css/new-books.css',
];

// Global-script entries (NOT bundled - they rely on window globals; esbuild
// tree-shakes them as side-effect-free imports). Minified individually so the
// script loading order and global side effects stay intact.
const jsEntries = {
  'categories.js': 'static/js/categories.js',
  'translations.js': 'static/js/translations.js',
  'book-i18n.js': 'static/js/book-i18n.js',
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
  for (const f of readdirSync(DIST)) {
    if (
      f === 'manifest.json' ||
      f === 'app.min.css' ||
      f === 'categories.min.js' ||
      f === 'translations.min.js' ||
      f === 'book-i18n.min.js' ||
      f === 'base.min.js' ||
      f === 'index.min.js' ||
      f.startsWith('app.') ||
      f.startsWith('categories.') ||
      f.startsWith('translations.') ||
      f.startsWith('book-i18n.') ||
      f.startsWith('base.') ||
      f.startsWith('index.')
    ) {
      continue;
    }
    rmSync(join(DIST, f), { force: true });
  }
}

async function main() {
  if (WATCH) {
    console.log('[build-frontend] watch mode (initial build)');
    await buildOnce();
    return;
  }
  cleanup();
  await buildOnce();
}

main().catch((e) => {
  console.error('[build-frontend] FAILED:', e);
  process.exit(1);
});
