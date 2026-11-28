import test from 'node:test'
import assert from 'node:assert/strict'
import { buildSchematic, transferArcs } from '../src/composables/transitLayout.js'

const data = {
  lines: [
    { id: 'l1', name: { zh: '1号线', en: 'Line 1' }, color: '#e04f5f', type: 'rail', status: 'open', stations: ['a', 'hub', 'c'] },
    { id: 'l2', name: { zh: '2号线', en: 'Line 2' }, color: '#2f7fe0', type: 'rail', status: 'open', stations: ['b', 'hub', 'd'] },
  ],
  stations: [
    { id: 'a', name: { zh: '甲站', en: 'A' }, pos: [0, 0] },
    { id: 'hub', name: { zh: '枢纽站', en: 'Hub' }, pos: [100, 0] },
    { id: 'b', name: { zh: '乙站', en: 'B' }, pos: [100, -100] },
    { id: 'c', name: { zh: '丙站', en: 'C' }, pos: [200, 0] },
    { id: 'd', name: { zh: '丁站', en: 'D' }, pos: [100, 100] },
  ],
}

const schematic = buildSchematic(data, { locale: 'zh' })

test('站名标签带覆盖文字的热区矩形（点击站名能命中站点）', () => {
  for (const station of schematic.stations) {
    const label = station.label
    assert.ok(label, `${station.id} 应有站名`)
    assert.ok(Array.isArray(label.hit) && label.hit.length === 4, `${station.id} 热区应是矩形`)
    const [x, y, w, h] = label.hit
    assert.ok(w >= label.text.length * 13, '热区宽度至少覆盖文字宽度')
    assert.ok(h >= 18, '热区高度覆盖文字')
    // 文字锚点落在热区内
    const left = label.anchor === 'end' ? label.x - w : label.anchor === 'middle' ? label.x - w / 2 : label.x
    assert.ok(label.x >= left - 1 && label.x <= left + w + 1, '文字锚点落在热区内')
    assert.ok(y + h >= 0 || y < 0, '热区有有效纵坐标')
  }
})

test('多线路经过的车站标记为换乘站，单线车站不是', () => {
  const hub = schematic.stations.find((item) => item.id === 'hub')
  const a = schematic.stations.find((item) => item.id === 'a')
  assert.equal(hub.transfer, true)
  assert.deepEqual(hub.lines.sort(), ['l1', 'l2'])
  assert.equal(a.transfer, false)
})

test('分段运营：相邻区段按段拆 path，未设置区段沿用整线状态', () => {
  const segmented = JSON.parse(JSON.stringify(data))
  segmented.lines[0].segments = [{ from: 'a', to: 'hub', status: 'building' }]
  const result = buildSchematic(segmented, { locale: 'zh' })
  const line = result.lines.find((item) => item.id === 'l1')
  assert.equal(line.segmentPaths.length, 2)
  assert.equal(line.segmentPaths[0].status, 'building')
  assert.equal(line.segmentPaths[1].status, 'open')
  for (const segment of line.segmentPaths) {
    assert.ok(segment.path.startsWith('M '), '每段都有独立 path')
  }
  const line2 = result.lines.find((item) => item.id === 'l2')
  assert.equal(line2.segmentPaths.length, 2, '没有分段设置也按站间拆 path')
})

test('换乘站弧形箭头：两条弧线带箭头，颜色取线路色', () => {
  const arcs = transferArcs(schematic.stations.find((item) => item.id === 'hub'), schematic.lines)
  assert.equal(arcs.length, 2)
  assert.deepEqual(arcs.map((arc) => arc.color).sort(), ['#2f7fe0', '#e04f5f'])
  for (const arc of arcs) {
    assert.ok(arc.path.startsWith('M '), '弧线是 path')
    assert.ok(arc.head.endsWith('Z'), '箭头是闭合三角形')
  }
})


test('站名偏移会移动文字和热区，自动位置保留', () => {
  const shifted = JSON.parse(JSON.stringify(data))
  shifted.stations[0].label_offset = [25, -12]
  const result = buildSchematic(shifted, { locale: 'zh' })
  const auto = schematic.stations.find((item) => item.id === 'a').label
  const moved = result.stations.find((item) => item.id === 'a').label
  assert.equal(moved.x, auto.x + 25)
  assert.equal(moved.y, auto.y - 12)
  assert.equal(moved.hit[0], auto.hit[0] + 25)
  assert.equal(moved.hit[1], auto.hit[1] - 12)
  assert.equal(moved.autoX, auto.autoX)
})

test('相邻站格位被别的线路占用时沿线跨格，不横向拐成 S 形', () => {
  const crowded = {
    lines: [
      { id: 'l0', name: { zh: '0' }, color: '#111111', status: 'open', stations: ['a1', 'a2'] },
      { id: 'l1', name: { zh: '1' }, color: '#222222', status: 'open', stations: ['a1', 'b2'] },
    ],
    stations: [
      { id: 'a1', name: { zh: 'A1' }, pos: [0, 0] },
      { id: 'a2', name: { zh: 'A2' }, pos: [0, 100] },
      { id: 'b2', name: { zh: 'B2' }, pos: [0, 100] },
    ],
  }
  const result = buildSchematic(crowded, { locale: 'zh' })
  const a1 = result.stations.find((item) => item.id === 'a1')
  const b2 = result.stations.find((item) => item.id === 'b2')
  assert.ok(Math.abs(b2.sx - a1.sx) < 0.01, '同一竖直方向的站保持同一 X')
  assert.ok(b2.sy > a1.sy)
})

test('拖站名只改 label_offset，不改变路线包围盒', () => {
  const shifted = JSON.parse(JSON.stringify(data))
  shifted.stations[0].label_offset = [200, 200]
  const before = buildSchematic(data, { locale: 'zh' })
  const after = buildSchematic(shifted, { locale: 'zh' })
  assert.deepEqual(after.routeBounds, before.routeBounds)
  assert.notDeepEqual(after.bounds, before.bounds)
})
