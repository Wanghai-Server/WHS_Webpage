/**
 * 轨交数据三方合并（与 data/transit.py 的 merge_three_way 同语义）。
 *
 * 背景：冲突重提时不能直接用「当前版本」当 base，否则会覆盖对方在
 * 非冲突字段上的修改。这里在浏览器里把 base → 本地 的改动重放到
 * 当前版本上，冲突字段按用户选择保留「我的」或「线上」。
 */

const MISSING = Symbol('missing')

function stable(value) {
  if (Array.isArray(value)) return value.map(stable)
  if (value && typeof value === 'object') {
    const out = {}
    for (const key of Object.keys(value).sort()) out[key] = stable(value[key])
    return out
  }
  return value
}

function canonical(value) {
  return JSON.stringify(stable(value))
}

function eq(a, b) {
  if (a === MISSING || b === MISSING) return a === b
  return canonical(a) === canonical(b)
}

function flatten(value, prefix = '', out = {}) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const key of Object.keys(value)) {
      flatten(value[key], prefix ? `${prefix}.${key}` : key, out)
    }
  } else if (prefix) {
    out[prefix] = value
  }
  return out
}

function unflatten(flat) {
  const root = {}
  for (const path of Object.keys(flat).sort()) {
    const parts = path.split('.')
    let node = root
    for (const part of parts.slice(0, -1)) {
      if (!node[part] || typeof node[part] !== 'object') node[part] = {}
      node = node[part]
    }
    node[parts[parts.length - 1]] = flat[path]
  }
  return root
}

function clone(value) {
  return value === undefined ? value : JSON.parse(JSON.stringify(value))
}

function mergeObject(base, current, incoming, where, conflicts) {
  if (eq(base, current)) return incoming
  if (eq(base, incoming)) return current
  if (eq(current, incoming)) return current
  if (current == null || incoming == null) {
    conflicts.push({ path: where, base, current, incoming, reason: 'deleted' })
    return current
  }
  if (base == null) base = {}
  const fb = flatten(base || {})
  const fc = flatten(current)
  const fi = flatten(incoming)
  const merged = {}
  const paths = new Set([...Object.keys(fb), ...Object.keys(fc), ...Object.keys(fi)])
  for (const path of [...paths].sort()) {
    const bv = path in fb ? fb[path] : MISSING
    const cv = path in fc ? fc[path] : MISSING
    const iv = path in fi ? fi[path] : MISSING
    let value
    if (eq(cv, iv)) value = cv
    else if (eq(bv, cv)) value = iv
    else if (eq(bv, iv)) value = cv
    else {
      conflicts.push({
        path: `${where}.${path}`,
        base: bv === MISSING ? null : bv,
        current: cv === MISSING ? null : cv,
        incoming: iv === MISSING ? null : iv,
      })
      value = cv
    }
    if (value !== MISSING) merged[path] = value
  }
  return Object.keys(merged).length ? unflatten(merged) : null
}

function mergeCollection(base, current, incoming, kind, conflicts) {
  const index = (items) => {
    const map = {}
    for (const item of items || []) if (item && item.id) map[item.id] = item
    return map
  }
  const bc = index(base)
  const cc = index(current)
  const ic = index(incoming)
  const result = []
  const keys = new Set([...Object.keys(bc), ...Object.keys(cc), ...Object.keys(ic)])
  for (const key of [...keys].sort()) {
    const merged = mergeObject(bc[key], cc[key], ic[key], `${kind}[${key}]`, conflicts)
    if (merged) result.push(merged)
  }
  const order = {}
  ;(incoming || []).forEach((item, pos) => { if (item && item.id) order[item.id] = pos })
  result.sort((a, b) => (order[a.id] ?? 1e6) - (order[b.id] ?? 1e6) || String(a.id).localeCompare(String(b.id)))
  return result
}

/** 返回 { data, conflicts }；data 已按「当前」为底、重放本地改动。 */
export function mergeThreeWay(base, current, incoming) {
  const conflicts = []
  const merged = {}
  merged.lines = mergeCollection(base?.lines, current?.lines, incoming?.lines, 'lines', conflicts)
  merged.stations = mergeCollection(base?.stations, current?.stations, incoming?.stations, 'stations', conflicts)
  const note = mergeObject(base?.note, current?.note, incoming?.note, 'note', conflicts)
  if (note) merged.note = note
  return { data: merged, conflicts, resolved: clone(current) }
}

/** 把某个路径强制设为「我的值」（用于冲突面板的 keep-mine）。 */
export function applyIncoming(data, path, value) {
  const match = /^(lines|stations)\[([^\]]+)\](?:\.(.+))?$/.exec(path)
  if (!match) return data
  const [, kind, id, rest] = match
  const list = data[kind] || []
  if (rest === undefined) {
    if (value == null) data[kind] = list.filter((item) => item.id !== id)
    else {
      const target = list.find((item) => item.id === id)
      if (!target) list.push(clone(value))
      else Object.assign(target, clone(value))
    }
    return data
  }
  const target = list.find((item) => item.id === id)
  if (!target) return data
  const parts = rest.split('.')
  let node = target
  for (const part of parts.slice(0, -1)) {
    if (!node[part] || typeof node[part] !== 'object') node[part] = {}
    node = node[part]
  }
  node[parts[parts.length - 1]] = value == null ? '' : clone(value)
  return data
}
