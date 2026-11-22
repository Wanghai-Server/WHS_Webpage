/**
 * 轨交路线图布局：把版本数据排成示意图坐标并生成 SVG path。
 *
 * 约定：
 * - 相邻两站的真实坐标差只用来决定**方向**，量化到 15° 网格（0 / 15 / 30 / 45 / 60 / 75 / 90 …）；
 * - 站间距固定，所以图上的距离 ≠ 实际距离，示意图只表达拓扑与换乘关系；
 * - 转角用二次贝塞尔削圆：非站点拐点半径 28，站点处用小半径（10），保证站点圆点仍压在线上；
 * - 换乘处需要跳到别的线路已占用的坐标时，枚举方向找一个「两段都落网格」的拐点。
 */

const STEP = 76
const CORNER_RADIUS = 28
const STATION_RADIUS = 16
const LABEL_SIZE = 13
const GRID = 15 // 方向量化粒度（度）

const DIRS = Array.from({ length: 360 / GRID }, (_, index) => {
  const angle = (index * GRID * Math.PI) / 180
  return [Math.cos(angle), Math.sin(angle)]
})

function keyOf([x, y]) {
  return `${Math.round(x)},${Math.round(y)}`
}

function snapVector(dx, dy) {
  if (!dx && !dy) return [1, 0]
  const index = Math.round(Math.atan2(dy, dx) / ((GRID * Math.PI) / 180))
  return DIRS[((index % DIRS.length) + DIRS.length) % DIRS.length]
}

function distance(a, b) {
  return Math.hypot(b[0] - a[0], b[1] - a[1])
}

/** 两段走线：从 a 到 b，找一个方向都为 15° 网格的拐点；找不到返回 []。 */
function snappedBridge(a, b) {
  if (!a || !b) return []
  let best = null
  for (const [ux, uy] of DIRS) {
    const t = (b[0] - a[0]) * ux + (b[1] - a[1]) * uy
    if (t <= 0) continue
    const corner = [a[0] + ux * t, a[1] + uy * t]
    const rest = distance(corner, b)
    if (rest < 1) continue
    const [vx, vy] = snapVector(b[0] - corner[0], b[1] - corner[1])
    const aligned = Math.abs((b[0] - corner[0]) * vy - (b[1] - corner[1]) * vx) < 2
    if (!aligned) continue
    const total = t + rest
    if (!best || total < best.total) best = { corner, total }
  }
  return best ? [best.corner] : []
}

/** 把折线点转成带圆角的 SVG path。`stationIndexes` 里的拐点用更小的半径。 */
function roundedPath(points, stationIndexes) {
  if (!points.length) return ''
  const commands = [`M ${round(points[0][0])} ${round(points[0][1])}`]
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1]
    const corner = points[index]
    const next = points[index + 1]
    if (!next) {
      commands.push(`L ${round(corner[0])} ${round(corner[1])}`)
      continue
    }
    const inLength = distance(previous, corner)
    const outLength = distance(corner, next)
    if (inLength < 0.5 || outLength < 0.5) {
      commands.push(`L ${round(corner[0])} ${round(corner[1])}`)
      continue
    }
    const inDir = [(corner[0] - previous[0]) / inLength, (corner[1] - previous[1]) / inLength]
    const outDir = [(next[0] - corner[0]) / outLength, (next[1] - corner[1]) / outLength]
    const cross = inDir[0] * outDir[1] - inDir[1] * outDir[0]
    if (Math.abs(cross) < 1e-3) {
      commands.push(`L ${round(corner[0])} ${round(corner[1])}`)
      continue
    }
    const isStation = stationIndexes.has(index)
    const radius = Math.min(isStation ? STATION_RADIUS : CORNER_RADIUS, inLength / 2, outLength / 2)
    const enter = [corner[0] - inDir[0] * radius, corner[1] - inDir[1] * radius]
    const leave = [corner[0] + outDir[0] * radius, corner[1] + outDir[1] * radius]
    commands.push(`L ${round(enter[0])} ${round(enter[1])}`)
    commands.push(`Q ${round(corner[0])} ${round(corner[1])} ${round(leave[0])} ${round(leave[1])}`)
  }
  return commands.join(' ')
}

function round(value) {
  return Math.round(value * 10) / 10
}

function textWidth(text) {
  let width = 0
  for (const char of String(text || '')) {
    width += /[\u2e80-\u9fff\uff00-\uffef]/.test(char) ? LABEL_SIZE : LABEL_SIZE * 0.55
  }
  return width
}

function overlap(a, b) {
  return a[0] < b[0] + b[2] && b[0] < a[0] + a[2] && a[1] < b[1] + b[3] && b[1] < a[1] + a[3]
}

/** 按当前语言取站名（缺一种回退另一种）。 */
export function stationName(station, locale) {
  return station?.name?.[locale] || station?.name?.zh || station?.name?.en || station?.id || ''
}

export function lineName(line, locale) {
  return line?.name?.[locale] || line?.name?.zh || line?.name?.en || line?.id || ''
}

/** 站名 / 线路名检索（中英 + id）。 */
export function matchStations(stations, keyword) {
  const query = String(keyword || '').trim().toLowerCase()
  if (!query) return []
  return stations.filter((station) => [station.name?.zh, station.name?.en, station.id]
    .some((name) => String(name || '').toLowerCase().includes(query)))
}

/**
 * 计算示意图。
 * @param {object} data `/api/map/transit` 的 data 段（lines / stations）
 * @param {{ locale?: string, step?: number }} options
 */
export function buildSchematic(data, options = {}) {
  const locale = options.locale || 'zh'
  const step = options.step || STEP
  const sourceStations = (data?.stations || []).map((item) => ({ ...item }))
  const byId = new Map(sourceStations.map((item) => [item.id, item]))
  const placed = new Map()
  const occupied = new Map()
  const stationLines = new Map()
  const lines = []

  for (const line of data?.lines || []) {
    const points = []
    const stationIndexes = new Set()
    let previous = null

    for (const stationId of line.stations) {
      const station = byId.get(stationId)
      if (!station) continue
      if (!stationLines.has(stationId)) stationLines.set(stationId, [])
      stationLines.get(stationId).push(line.id)

      let point = placed.get(stationId)
      if (!point) {
        const dir = previous ? snapVector(station.pos[0] - previous.pos[0], station.pos[1] - previous.pos[1]) : [1, 0]
        const base = points.length ? points[points.length - 1] : [0, 0]
        point = [base[0] + dir[0] * step, base[1] + dir[1] * step]
        let guard = 0
        while (occupied.has(keyOf(point)) && occupied.get(keyOf(point)) !== stationId && guard < 12) {
          point = [point[0] + dir[1] * step, point[1] - dir[0] * step]
          guard += 1
        }
        placed.set(stationId, point)
        occupied.set(keyOf(point), stationId)
      } else if (points.length) {
        points.push(...snappedBridge(points[points.length - 1], point))
      }

      points.push([...point])
      stationIndexes.add(points.length - 1)
      previous = station
    }

    // 去掉连续重复点（换乘补角可能产生重合点）
    const clean = points.filter((point, index) => {
      if (!index) return true
      const prev = points[index - 1]
      return Math.abs(point[0] - prev[0]) > 0.01 || Math.abs(point[1] - prev[1]) > 0.01
    })
    const path = roundedPath(clean, stationIndexes)
    if (!path) continue
    lines.push({ ...line, path, points: clean })
  }

  const used = sourceStations.filter((station) => placed.has(station.id) && stationLines.get(station.id)?.length)
  const labels = []
  const labelRects = []

  for (const station of used) {
    const [x, y] = placed.get(station.id)
    const text = stationName(station, locale)
    const width = textWidth(text)
    const candidates = [
      { anchor: 'start', x: x + 14, y: y + 5, rect: [x + 12, y - 8, width + 6, 18] },
      { anchor: 'end', x: x - 14, y: y + 5, rect: [x - 14 - width - 6, y - 8, width + 6, 18] },
      { anchor: 'middle', x, y: y - 15, rect: [x - width / 2 - 3, y - 27, width + 6, 18] },
      { anchor: 'middle', x, y: y + 21, rect: [x - width / 2 - 3, y + 9, width + 6, 18] },
    ]
    const pick = candidates.find((item) => !labelRects.some((rect) => overlap(rect, item.rect))) || candidates[0]
    labelRects.push(pick.rect)
    labels.push({ id: station.id, text, x: pick.x, y: pick.y, anchor: pick.anchor })
  }

  const labelById = new Map(labels.map((item) => [item.id, item]))
  const stations = used.map((station) => {
    const [x, y] = placed.get(station.id)
    const ids = stationLines.get(station.id) || []
    const first = lines.find((line) => line.id === ids[0])
    return {
      ...station,
      x,
      y,
      lines: ids,
      transfer: ids.length > 1,
      color: first?.color || '#888888',
      label: labelById.get(station.id),
    }
  })

  return {
    lines,
    stations,
    bounds: measure([...lines.flatMap((line) => line.points), ...stations.map((item) => [item.x, item.y])], labelRects),
    note: data?.note || null,
  }
}

function measure(points, rects) {
  const xs = []
  const ys = []
  for (const [x, y] of points) {
    xs.push(x)
    ys.push(y)
  }
  for (const rect of rects) {
    xs.push(rect[0], rect[0] + rect[2])
    ys.push(rect[1], rect[1] + rect[3])
  }
  if (!xs.length) return { x: 0, y: 0, width: 480, height: 280 }
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  return {
    x: minX - 32,
    y: minY - 32,
    width: Math.max(...xs) - minX + 64,
    height: Math.max(...ys) - minY + 64,
  }
}
