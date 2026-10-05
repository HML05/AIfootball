import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Lang = 'en' | 'zh'

const dict = {
  en: {
    'nav.Overview': 'Overview', 'nav.Leagues': 'Leagues', 'nav.Teams': 'Teams', 'nav.Players': 'Players',
    'nav.Predict': 'Predict', 'nav.Agent': 'AI Agent', 'nav.Live': 'Live', 'nav.Reports': 'Reports',
    'topbar.configs': 'Configs',
    'greeting.prefix': 'Welcome to ',
    'stats.Matches': 'Matches', 'stats.Players': 'Players', 'stats.Accuracy': 'Accuracy', 'stats.Models': 'Models',
    'stats.Teams': 'Teams', 'stats.Events': 'Events (10k)', 'stats.Tables': 'Tables',
    'card.Activity': 'Top Scorers', 'card.Focus timer': 'Model Accuracy', 'card.Induction': 'Match Prediction',
    'activity.caption': 'Goals this season\nTop 7 scorers',
    'focus.mode': 'Ensemble v4 · out-of-sample',
    'profile.role': 'Premier League · Round 28 · Etihad',
    'match.home': 'Home', 'match.draw': 'Draw', 'match.away': 'Away',
    'menu.premier-league': 'Premier League', 'menu.la-liga': 'LaLiga', 'menu.bundesliga': 'Bundesliga',
    'menu.serie-a': 'Serie A', 'menu.ligue-1': 'Ligue 1',
    'pending.title': 'Update Log',
    'pending.sync': '赛程同步完成', 'pending.live': '实时比分入库', 'pending.api': '外部 API 限流',
    'pending.retrain': '模型重训练', 'pending.odds': '赔率数据同步',
    'pending.sync.time': '03-09 06:12 · 480 fixtures written',
    'pending.live.time': '03-08 23:40 · 32 matches, 214 events',
    'pending.api.time': '03-08 18:05 · 429 rate-limited, retried',
    'pending.retrain.time': '03-08 06:12 · Acc 55.1% (+0.6pp)',
    'pending.odds.time': '03-07 06:12 · 960 odds records',
    'cal.prev': 'February', 'cal.current': 'March 2026', 'cal.next': 'April',
    'cal.days': 'Fri,Sat,Sun,Mon,Tue,Wed',
    'event.city.title': 'Man City vs Arsenal', 'event.city.subtitle': 'Prediction 2-1 · Conf 0.71',
    'event.derby.title': 'Inter vs Napoli', 'event.derby.subtitle': 'Prediction 1-0 · Conf 0.66',
    'switcher.user': 'User', 'switcher.admin': 'Admin',
    'switcher.userView': 'User view', 'switcher.adminView': 'Admin view',
    'switcher.lang': 'Switch language', 'switcher.theme': 'Switch theme',
    // admin
    'admin.greeting.prefix': 'Data Overview, ',
    'admin.subtitle': 'Football analytics & AI prediction · admin console',
    'admin.kpi.matches': 'Matches', 'admin.kpi.players': 'Players',
    'admin.kpi.events': 'Match Events', 'admin.kpi.predictions': 'Predictions',
    'admin.vsLastMonth': 'this month',
    'admin.trend.title': 'Ingestion Trend', 'admin.trend.caption': 'Last 12 weeks · 10k records',
    'admin.trend.week': 'W',
    'admin.dept.title': 'Data Distribution', 'admin.dept.caption': 'By record type',
    'cls.events': 'Match events', 'cls.passes': 'Passing data', 'cls.playerStats': 'Player stats', 'cls.others': 'Other data',
    'admin.funnel.title': 'Data Pipeline', 'admin.funnel.caption': 'Raw → predictions',
    'admin.funnel.passes': 'Passes', 'admin.funnel.events': 'Match events',
    'admin.funnel.shots': 'Shots', 'admin.funnel.predictions': 'Predictions',
    'admin.bands.title': 'Goals by Minute', 'admin.bands.caption': 'This season · 0-90′',
    'admin.table.title': 'Model Registry', 'admin.table.caption': '4 models · out-of-sample',
    'admin.table.name': 'Model', 'admin.table.algo': 'Algorithm', 'admin.table.acc': 'Accuracy',
    'admin.table.logloss': 'LogLoss', 'admin.table.brier': 'Brier', 'admin.table.status': 'Status',
    'admin.status.production': 'Production', 'admin.status.challenger': 'Challenger', 'admin.status.baseline': 'Baseline',
  },
  zh: {
    'nav.Overview': '总览', 'nav.Leagues': '联赛', 'nav.Teams': '球队', 'nav.Players': '球员',
    'nav.Predict': '预测', 'nav.Agent': 'AI 分析', 'nav.Live': '实时', 'nav.Reports': '报告',
    'topbar.configs': '设置',
    'greeting.prefix': '欢迎使用 ',
    'stats.Matches': '收录比赛', 'stats.Players': '球员样本', 'stats.Accuracy': '预测准确率', 'stats.Models': '在线模型',
    'stats.Teams': '收录球队', 'stats.Events': '事件(万条)', 'stats.Tables': '数据表',
    'card.Activity': '射手榜', 'card.Focus timer': '预测准确率', 'card.Induction': '焦点战预测',
    'activity.caption': '本赛季进球\nTop 7 射手',
    'focus.mode': '集成模型 v4 · 样本外',
    'profile.role': '英超 · 第 28 轮 · 伊蒂哈德球场',
    'match.home': '主胜', 'match.draw': '平局', 'match.away': '客胜',
    'menu.premier-league': '英超', 'menu.la-liga': '西甲', 'menu.bundesliga': '德甲',
    'menu.serie-a': '意甲', 'menu.ligue-1': '法甲',
    'pending.title': '更新日志',
    'pending.sync': '赛程同步完成', 'pending.live': '实时比分入库', 'pending.api': '外部 API 限流',
    'pending.retrain': '模型重训练', 'pending.odds': '赔率数据同步',
    'pending.sync.time': '03-09 06:12 · 写入 480 场赛程与结果',
    'pending.live.time': '03-08 23:40 · 32 场比赛，214 条事件',
    'pending.api.time': '03-08 18:05 · 触发 429，已退避重试',
    'pending.retrain.time': '03-08 06:12 · 准确率 55.1%（+0.6pp）',
    'pending.odds.time': '03-07 06:12 · 960 条赔率记录',
    'cal.prev': '二月', 'cal.current': '2026 年 3 月', 'cal.next': '四月',
    'cal.days': '周五,周六,周日,周一,周二,周三',
    'event.city.title': '曼城 vs 阿森纳', 'event.city.subtitle': '预测 2-1 · 置信度 0.71',
    'event.derby.title': '国际米兰 vs 那不勒斯', 'event.derby.subtitle': '预测 1-0 · 置信度 0.66',
    'switcher.user': '用户端', 'switcher.admin': '管理端',
    'switcher.userView': '切换到用户界面', 'switcher.adminView': '切换到管理后台',
    'switcher.lang': '切换语言', 'switcher.theme': '切换深浅色',
    // admin
    'admin.greeting.prefix': '数据概览，',
    'admin.subtitle': '足球数据分析与 AI 预测系统 · 管理后台',
    'admin.kpi.matches': '收录比赛', 'admin.kpi.players': '球员样本',
    'admin.kpi.events': '比赛事件', 'admin.kpi.predictions': '预测样本',
    'admin.vsLastMonth': '本月',
    'admin.trend.title': '入库趋势', 'admin.trend.caption': '近 12 周 · 万条',
    'admin.trend.week': 'W',
    'admin.dept.title': '数据分布', 'admin.dept.caption': '按记录类型',
    'cls.events': '比赛事件', 'cls.passes': '传球数据', 'cls.playerStats': '球员统计', 'cls.others': '其他数据',
    'admin.funnel.title': '数据管道', 'admin.funnel.caption': '原始数据 → 预测',
    'admin.funnel.passes': '传球记录', 'admin.funnel.events': '比赛事件',
    'admin.funnel.shots': '射门记录', 'admin.funnel.predictions': '预测样本',
    'admin.bands.title': '进球时段分布', 'admin.bands.caption': '本赛季 · 0-90 分钟',
    'admin.table.title': '模型注册表', 'admin.table.caption': '4 个模型 · 样本外评估',
    'admin.table.name': '模型', 'admin.table.algo': '算法', 'admin.table.acc': '准确率',
    'admin.table.logloss': 'LogLoss', 'admin.table.brier': 'Brier', 'admin.table.status': '状态',
    'admin.status.production': '生产环境', 'admin.status.challenger': '挑战者', 'admin.status.baseline': '基线',
  },
} as const

export type I18nKey = keyof (typeof dict)['en']

interface LangCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: I18nKey) => string
}

const LangContext = createContext<LangCtx>({ lang: 'en', setLang: () => {}, t: (k) => k })

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const q = new URLSearchParams(window.location.search).get('lang')
    if (q === 'zh' || q === 'en') return q
    return (localStorage.getItem('talvex-lang') as Lang) || 'en'
  })
  const setLang = (l: Lang) => {
    setLangState(l)
    localStorage.setItem('talvex-lang', l)
  }
  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])
  const t = (key: I18nKey) => dict[lang][key] ?? key
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>
}

export const useLang = () => useContext(LangContext)
