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
const rows = []
for (const f of files) {
  const src = readFileSync(f, 'utf8')
  const body = (src.match(/<style[\s\S]*?<\/style>/g) || []).join('\n')
  const hex = (body.match(/#[0-9a-fA-F]{3,8}\b/g) || []).length
  const rgb = (body.match(/\brgba?\(/g) || []).length
  const n = hex + rgb
  if (n) rows.push([f.split(path.sep).join('/'), n])
}
rows.sort((a, b) => b[1] - a[1])
console.log('files with literals:', rows.length)
console.log(
  'total literals:',
  rows.reduce((s, r) => s + r[1], 0)
)
console.log(JSON.stringify(Object.fromEntries(rows), null, 2))
