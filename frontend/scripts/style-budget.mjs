import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return walk(p)
    return p.endsWith('.vue') ? [p] : []
  })
}

const files = [...walk('src/views'), ...walk('src/layouts')]

/* Colour literals hide in three places, and tests/unit/styleDebtRatchet.test.js budgets
   each one separately. Print all three so regenerating a quota cannot quietly drop the
   other two. The template block is everything before <script — a lazy `</template>`
   match would stop at the first slot template and under-count. */
const BLOCKS = {
  hardcodedColorLiterals: (src) => (src.match(/<style[\s\S]*?<\/style>/g) || []).join('\n'),
  scriptColorLiterals: (src) => (src.match(/<script[\s\S]*?<\/script>/g) || []).join('\n'),
  templateColorLiterals: (src) => {
    const at = src.search(/<script/)
    return at < 0 ? src : src.slice(0, at)
  },
}

const countIn = (text) =>
  (text.match(/#[0-9a-fA-F]{3,8}\b/g) || []).length + (text.match(/\brgba?\(/g) || []).length

for (const [budget, block] of Object.entries(BLOCKS)) {
  const rows = files
    .map((f) => [f.split(path.sep).join('/'), countIn(block(readFileSync(f, 'utf8')))])
    .filter(([, n]) => n)
    .sort((a, b) => b[1] - a[1])
  console.log(`\n${budget}: ${rows.length} files, ${rows.reduce((s, r) => s + r[1], 0)} literals`)
  console.log(JSON.stringify(Object.fromEntries(rows), null, 2))
}
