/**
 * 展示层文案映射（上游英文枚举 → 中文界面文案）。
 * 只做「显示」，不改接口数据；未收录的值原样返回，避免吞掉未知取值。
 */
import { pick } from '../data/live'
import type { Lang } from '../i18n'

export const POSITION_LABEL: Record<string, [string, string]> = {
  goalkeeper: ['门将', 'Goalkeeper'],
  defender: ['后卫', 'Defender'],
  'centre-back': ['中后卫', 'Centre-Back'],
  'center-back': ['中后卫', 'Center-Back'],
  'left-back': ['左后卫', 'Left-Back'],
  'right-back': ['右后卫', 'Right-Back'],
  'full-back': ['边后卫', 'Full-Back'],
  midfielder: ['中场', 'Midfielder'],
  midfield: ['中场', 'Midfield'],
  'defensive midfield': ['后腰', 'Defensive Midfield'],
  'central midfield': ['中前卫', 'Central Midfield'],
  'attacking midfield': ['前腰', 'Attacking Midfield'],
  'left midfield': ['左前卫', 'Left Midfield'],
  'right midfield': ['右前卫', 'Right Midfield'],
  attacker: ['前锋', 'Attacker'],
  attack: ['前锋', 'Attack'],
  forward: ['前锋', 'Forward'],
  striker: ['中锋', 'Striker'],
  'centre-forward': ['中锋', 'Centre-Forward'],
  'center-forward': ['中锋', 'Center-Forward'],
  'second striker': ['影锋', 'Second Striker'],
  'left wing': ['左边锋', 'Left Wing'],
  'right wing': ['右边锋', 'Right Wing'],
  'left winger': ['左边锋', 'Left Winger'],
  'right winger': ['右边锋', 'Right Winger'],
  winger: ['边锋', 'Winger'],
}

/** 位置原文 → 当前语言文案（未收录按原文） */
export function posLabel(lang: Lang, position: string | null | undefined, fallback = '—'): string {
  if (!position) return fallback
  const hit = POSITION_LABEL[position.trim().toLowerCase()]
  return hit ? pick(lang, hit[0], hit[1]) : position
}

export const FOOT_LABEL: Record<string, [string, string]> = {
  left: ['左脚', 'Left'],
  right: ['右脚', 'Right'],
  both: ['双脚', 'Both'],
}

export function footLabel(lang: Lang, foot: string | null | undefined, fallback = '—'): string {
  if (!foot) return fallback
  const hit = FOOT_LABEL[foot.trim().toLowerCase()]
  return hit ? pick(lang, hit[0], hit[1]) : foot
}
