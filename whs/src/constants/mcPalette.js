/**
 * 线路颜色预设：Minecraft 染色方块（羊毛 / 混凝土 / 混凝土粉末 / 染色玻璃 / 染色陶瓦）。
 *
 * 游戏里的线路颜色基本都取自这几类染色方块，所以按方块类别分 5 组、每组 16 色，
 * 另外允许手填 #RRGGBB。色值按方块平均色整理，允许后续按实拍微调。
 */

export const DYE_NAMES = [
  { key: 'white', zh: '白色', en: 'White' },
  { key: 'orange', zh: '橙色', en: 'Orange' },
  { key: 'magenta', zh: '品红', en: 'Magenta' },
  { key: 'light_blue', zh: '淡蓝', en: 'Light Blue' },
  { key: 'yellow', zh: '黄色', en: 'Yellow' },
  { key: 'lime', zh: '黄绿', en: 'Lime' },
  { key: 'pink', zh: '粉红', en: 'Pink' },
  { key: 'gray', zh: '灰色', en: 'Gray' },
  { key: 'light_gray', zh: '淡灰', en: 'Light Gray' },
  { key: 'cyan', zh: '青色', en: 'Cyan' },
  { key: 'purple', zh: '紫色', en: 'Purple' },
  { key: 'blue', zh: '蓝色', en: 'Blue' },
  { key: 'brown', zh: '棕色', en: 'Brown' },
  { key: 'green', zh: '绿色', en: 'Green' },
  { key: 'red', zh: '红色', en: 'Red' },
  { key: 'black', zh: '黑色', en: 'Black' },
]

export const PALETTE_FAMILIES = [
  {
    key: 'wool',
    zh: '羊毛',
    en: 'Wool',
    colors: ['#E9ECEC', '#F07613', '#BD44B3', '#3AAFD9', '#F8C627', '#70B919', '#ED8DAC', '#3E4447',
      '#8E8E86', '#158991', '#792AAC', '#35399D', '#724728', '#546D1B', '#A12722', '#141519'],
  },
  {
    key: 'concrete',
    zh: '混凝土',
    en: 'Concrete',
    colors: ['#CFD5D6', '#E06100', '#A9309F', '#2389C6', '#F0AF15', '#5EA818', '#D5658F', '#373A3E',
      '#7D7D73', '#157788', '#64209C', '#2C2E8F', '#603C20', '#495B24', '#8E2121', '#080A0F'],
  },
  {
    key: 'powder',
    zh: '混凝土粉末',
    en: 'Concrete Powder',
    colors: ['#E2E4E4', '#E38423', '#C35BC3', '#4AA9D2', '#F7D06B', '#9FD74F', '#F1A7C2', '#7C7C72',
      '#B5B6B0', '#2696A6', '#A152BD', '#4A5AC4', '#8C5A32', '#6E8C36', '#B04A38', '#1A1C1F'],
  },
  {
    key: 'glass',
    zh: '染色玻璃',
    en: 'Stained Glass',
    colors: ['#F2F2F2', '#FF9E33', '#E361DB', '#66C3F0', '#FFE45C', '#9BE04C', '#F7A1C3', '#4E5559',
      '#A9ABA6', '#2FA6B2', '#9A5BC4', '#4D5FD0', '#8C6A46', '#6A8F32', '#C93F3A', '#2A2D31'],
  },
  {
    key: 'terracotta',
    zh: '染色陶瓦',
    en: 'Stained Terracotta',
    colors: ['#D1B1A1', '#A3541B', '#96586D', '#706C8A', '#B98420', '#677535', '#A24F4F', '#392A23',
      '#876A61', '#575A5B', '#764656', '#4A3B5A', '#4D3323', '#4C532A', '#8E3C2E', '#251610'],
  },
]

export function familyLabel(family, locale) {
  return locale === 'en' ? family.en : family.zh
}

export function dyeLabel(index, locale) {
  const dye = DYE_NAMES[index] || DYE_NAMES[0]
  return locale === 'en' ? dye.en : dye.zh
}
