import '../App.css'
import TopNav from '../sections/TopNav'
import StatsRow from '../sections/StatsRow'
import { ProfileCard, SideMenu } from '../sections/LeftColumn'
import { ActivityCard, FocusTimerCard, PredictionTrustCard } from '../sections/MiddleCards'
import CalendarCard from '../sections/CalendarCard'
import { RecentMatchesCard, UpcomingCard } from '../sections/StreamCards'
import { fmtNum, pick, useHome } from '../data/live'
import { useLang } from '../i18n'

export function Blobs() {
  return (
    <div className="blob-layer pointer-events-none fixed inset-0" aria-hidden>
      <div className="blob-a absolute -left-24 -top-24 h-[420px] w-[420px] rounded-full bg-[#F6C945]/35 blur-3xl" />
      <div className="blob-b absolute right-[-120px] top-[30%] h-[460px] w-[460px] rounded-full bg-[#E8B4B8]/30 blur-3xl" />
      <div className="blob-a absolute bottom-[-140px] left-[35%] h-[380px] w-[380px] rounded-full bg-[#A8C5E2]/25 blur-3xl" />
    </div>
  )
}

export default function Home() {
  const { lang } = useLang()
  const { data } = useHome()
  const cov = data?.coverage

  return (
    <div className="font-sans-talvex relative min-h-screen overflow-x-hidden">
      <Blobs />
      <div className="relative mx-auto max-w-[1400px] px-6 py-5 pb-24">
        <TopNav activePath="/" />

        <h1
          className="anim-in t-1 mt-7 text-[52px] font-medium leading-none tracking-[-0.03em]"
          style={{ '--d': '40ms' } as React.CSSProperties}
        >
          {pick(lang, '欢迎使用 ', 'Welcome to ')}
          <span className="font-semibold">{data?.brand.name ?? 'FootballAI'}</span>
        </h1>

        <p className="t-3 anim-in mt-2 text-[12px] font-medium tabular-nums" style={{ '--d': '70ms' } as React.CSSProperties}>
          {cov
            ? `${fmtNum(cov.matches)} ${pick(lang, '场比赛', 'matches')} · ${fmtNum(cov.finished)} ${pick(
                lang,
                '场已完赛',
                'finished',
              )} · ${fmtNum(cov.upcoming)} ${pick(lang, '场待赛', 'upcoming')} · ${fmtNum(cov.xofficial)} ${pick(
                lang,
                '场官方 xG',
                'with xG',
              )} · ${fmtNum(cov.predictions)} ${pick(lang, '条预测', 'predictions')} · ${pick(lang, '数据', 'range')} ${
                cov.rangeFrom.slice(0, 10)
              } ~ ${cov.rangeTo.slice(0, 10)}`
            : pick(lang, '正在载入真实数据…', 'Loading live data…')}
        </p>

        <StatsRow />

        <div className="mt-6 grid grid-cols-[250px_minmax(0,1fr)_300px] items-stretch gap-5">
          {/* 左列：焦点战（含推荐与三分类概率）+ 预测可信度 */}
          <div className="flex flex-col gap-5">
            <ProfileCard />
            <PredictionTrustCard />
          </div>

          {/* 中列：射手榜 + 准确率环 / 赛程日历 / 最近完赛 + 未来赛程 */}
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-5">
              <ActivityCard />
              <FocusTimerCard />
            </div>
            <CalendarCard />
            <div className="grid grid-cols-2 gap-5">
              <RecentMatchesCard />
              <UpcomingCard />
            </div>
          </div>

          {/* 右列：联赛积分榜（用户第一查询诉求） */}
          <div className="flex flex-col gap-5">
            <SideMenu />
          </div>
        </div>
      </div>
    </div>
  )
}
