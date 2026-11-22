import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeThreeWay } from '../src/composables/transitMerge.js'

function baseDoc() {
  return {
    lines: [
      { id: 'l1', name: { zh: '1号线', en: 'Line 1' }, color: '#2f7fe0', stations: ['a', 'b'] },
    ],
    stations: [
      { id: 'a', name: { zh: '甲', en: 'A' }, pos: [0, 0] },
      { id: 'b', name: { zh: '乙', en: 'B' }, pos: [100, 0] },
    ],
  }
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

test('双方改不同字段：两边的修改都保留', () => {
  const base = baseDoc()
  const current = clone(base)
  current.lines[0].name = { zh: '1号线（线上）', en: 'Line 1 live' }
  const incoming = clone(base)
  incoming.stations.push({ id: 'c', name: { zh: '丙', en: 'C' }, pos: [200, 0] })

  const { data, conflicts } = mergeThreeWay(base, current, incoming)
  assert.equal(conflicts.length, 0)
  assert.equal(data.lines[0].name.zh, '1号线（线上）')
  assert.ok(data.stations.find((item) => item.id === 'c'))
})

test('双方各自新增车站：两个都保留', () => {
  const base = baseDoc()
  const current = clone(base)
  current.stations.push({ id: 'qa', name: { zh: '甲2', en: 'QA' }, pos: [0, 50] })
  const incoming = clone(base)
  incoming.stations.push({ id: 'qb', name: { zh: '乙2', en: 'QB' }, pos: [50, 0] })

  const { data, conflicts } = mergeThreeWay(base, current, incoming)
  assert.equal(conflicts.length, 0)
  const ids = data.stations.map((item) => item.id).sort()
  assert.deepEqual(ids, ['a', 'b', 'qa', 'qb'])
})

test('同一字段双方都改：报冲突并默认保留线上值', () => {
  const base = baseDoc()
  const current = clone(base)
  current.lines[0].name = { zh: '线上名', en: 'Live' }
  const incoming = clone(base)
  incoming.lines[0].name = { zh: '我的名', en: 'Mine' }

  const { data, conflicts } = mergeThreeWay(base, current, incoming)
  // name.zh 与 name.en 都被双方修改：各报一条冲突
  assert.equal(conflicts.length, 2)
  assert.ok(conflicts.every((item) => /^lines\[l1\]\.name/.test(item.path)))
  assert.equal(data.lines[0].name.zh, '线上名')
})

test('删除与修改冲突：保留线上删除结果并报冲突', () => {
  const base = baseDoc()
  const current = clone(base)
  current.stations = current.stations.filter((item) => item.id !== 'b')
  const incoming = clone(base)
  incoming.stations.find((item) => item.id === 'b').name.zh = '改名'

  const { data, conflicts } = mergeThreeWay(base, current, incoming)
  assert.ok(conflicts.some((item) => item.path.startsWith('stations[b]')))
  assert.equal(data.stations.find((item) => item.id === 'b'), undefined)
})
