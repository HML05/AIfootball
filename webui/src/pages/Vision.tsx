/**
 * 视频分析（YOLOv8 检测 + 跟踪）
 *
 * 数据流: 上传视频 → 排一个任务(数据库 queued) → 本地 `.venv-vision` 里的
 * `scripts/run_vision_jobs.py` 领任务跑 → 抽样轨迹与指标写回数据库 → 这个页面用 canvas 叠框。
 *
 * 为什么不在页面上放「预渲染的带框视频」: 1500 帧要跑几分钟、单 worker 的 uvicorn 会被占住，
 * 而且云主机没有 GPU。所以框是**按时钟现画**的：video 播到第 t 秒 → 取 round(t*fps) 那一帧的
 * 抽样轨迹 → 画上去。轨迹是抽样入库的（默认每 5 帧一条），画的时候取最近的抽样帧。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Play, RefreshCw, Trash2, Upload, Video as VideoIcon } from 'lucide-react'
import {
  Bar,
  EmptyState,
  ErrorState,
  KpiStrip,
  PageShell,
  Pill,
  SectionCard,
} from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import {
  api,
  type VisionBox,
  type VisionJob,
  type VisionSummaryPayload,
  type VisionTracks,
  type VisionVideo,
} from '../lib/api'
import { clearApiCache, useApi } from '../lib/useApi'
import { useLang } from '../i18n'
import type { Lang } from '../i18n'
import { fmtNum, pick } from '../data/live'

const PERSON_COLOR = '#F6C945'
const BALL_COLOR = '#FF7AA2'

const fmtSize = (bytes: number | null | undefined): string => {
  if (!bytes) return '—'
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

const fmtDuration = (sec: number | null | undefined): string => {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s} 秒`
}

const STATUS_TONE: Record<string, 'muted' | 'yellow' | 'green' | 'pink' | 'blue'> = {
  uploaded: 'muted',
  queued: 'blue',
  running: 'yellow',
  done: 'green',
  failed: 'pink',
}

function statusText(lang: Lang, status: string): string {
  const m: Record<string, [string, string]> = {
    uploaded: ['待处理', 'Uploaded'],
    queued: ['排队中', 'Queued'],
    running: ['处理中', 'Running'],
    done: ['已完成', 'Done'],
    failed: ['失败', 'Failed'],
    canceled: ['已取消', 'Canceled'],
  }
  const pair = m[status] ?? [status, status]
  return pick(lang, pair[0], pair[1])
}

/** 在抽样帧里找 <= frame 的最后一帧（二分） */
function nearest(frames: { f: number; b: VisionBox[] }[], frame: number): number {
  if (!frames.length) return -1
  let lo = 0
  let hi = frames.length - 1
  let idx = 0
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (frames[mid].f <= frame) {
      idx = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return idx
}

export default function Vision() {
  const { lang } = useLang()
  const overview = useApi((s) => api.visionOverview(s), 'vision-overview', 15_000)
  const videos = useApi((s) => api.visionVideos(s), 'vision-videos', 15_000)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const items = videos.data?.items ?? []
  const selected: VisionVideo | null = useMemo(
    () => items.find((v) => v.video_id === selectedId) ?? items[0] ?? null,
    [items, selectedId],
  )
  const currentId = selected?.video_id ?? null

  // —— 任务进度：排队/处理中时每 2.5 s 拉一次，完成时刷新列表与轨迹缓存
  const [job, setJob] = useState<VisionJob | null>(null)
  useEffect(() => {
    setJob(selected?.job ?? null)
  }, [selected?.video_id, selected?.job?.job_id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return
    const timer = window.setInterval(async () => {
      try {
        const next = await api.visionJob(job.job_id)
        setJob(next)
        if (next.status === 'done' || next.status === 'failed' || next.status === 'canceled') {
          clearApiCache('vision-tracks')
          clearApiCache('vision-summary')
          videos.reload()
        }
      } catch {
        /* 轮询失败就等下一轮 */
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [job?.job_id, job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const doneJobId = selected?.done_job_id ?? null
  const tracksKey = currentId && doneJobId ? `vision-tracks-${currentId}-${doneJobId}` : 'vision-tracks-none'
  const tracks = useApi<VisionTracks | null>(
    (s) => (currentId && doneJobId ? api.visionTracks(currentId, doneJobId, s) : Promise.resolve(null)),
    tracksKey,
    300_000,
  )
  const summaryKey = currentId && doneJobId ? `vision-summary-${currentId}-${doneJobId}` : 'vision-summary-none'
  const summary = useApi<VisionSummaryPayload | null>(
    (s) => (currentId && doneJobId ? api.visionSummary(currentId, doneJobId, s) : Promise.resolve(null)),
    summaryKey,
    300_000,
  )

  // —— 上传 / 处理 / 删除
  const [busy, setBusy] = useState<'' | 'upload' | 'process' | 'delete'>('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [step, setStep] = useState(5)
  const fileRef = useRef<HTMLInputElement>(null)

  const worker = overview.data?.worker
  const running = job && (job.status === 'queued' || job.status === 'running')

  const onUpload = async (file: File) => {
    setBusy('upload')
    setActionError(null)
    setNotice(null)
    try {
      const created = await api.visionUpload(file)
      clearApiCache('vision-')
      videos.reload()
      overview.reload()
      setSelectedId(created.video_id)
      setNotice(pick(lang, `已上传 ${created.name}`, `Uploaded ${created.name}`))
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy('')
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const onProcess = async () => {
    if (!currentId) return
    setBusy('process')
    setActionError(null)
    setNotice(null)
    try {
      const created = await api.visionProcess(currentId, { step })
      setJob(created)
      videos.reload()
      setNotice(
        pick(
          lang,
          `任务 #${created.job_id} 已排队：现在去本机跑处理进程，它一领取就会开始`,
          `Job #${created.job_id} queued — start the worker locally to pick it up`,
        ),
      )
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy('')
    }
  }

  const onCancel = async () => {
    if (!job) return
    try {
      const next = await api.visionCancel(job.job_id)
      setJob(next)
      videos.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  const onDelete = async (v: VisionVideo) => {
    if (!window.confirm(pick(lang, `删除「${v.name}」及其所有结果？`, `Delete “${v.name}” and all its results?`))) return
    setBusy('delete')
    setActionError(null)
    try {
      await api.visionDelete(v.video_id)
      clearApiCache('vision-')
      videos.reload()
      overview.reload()
      setSelectedId(null)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy('')
    }
  }

  // —— canvas 叠框
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [showBoxes, setShowBoxes] = useState(true)
  const [showIds, setShowIds] = useState(true)
  const [showTrails, setShowTrails] = useState(true)
  const framesRef = useRef<{ f: number; b: VisionBox[] }[]>([])
  framesRef.current = tracks.data?.frames ?? []
  const fpsRef = useRef(25)
  fpsRef.current = selected?.fps || 25

  const draw = useCallback(() => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    const w = video.videoWidth
    const h = video.videoHeight
    if (!w || !h) return
    if (canvas.width !== w) canvas.width = w
    if (canvas.height !== h) canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, w, h)

    const frames = framesRef.current
    if (!frames.length) return
    const frame = Math.round(video.currentTime * fpsRef.current)
    const idx = nearest(frames, frame)
    if (idx < 0) return

    if (showTrails) {
      // 每个 ID 回看最近 12 个抽样帧，画一条折线
      const from = Math.max(0, idx - 12)
      const paths = new Map<number, [number, number][]>()
      for (let i = from; i <= idx; i += 1) {
        for (const b of frames[i].b) {
          if (b[0] === null) continue
          const cx = (b[3] + b[5]) / 2
          const cy = b[6]
          const list = paths.get(b[0]) ?? []
          list.push([cx, cy])
          paths.set(b[0], list)
        }
      }
      for (const [, pts] of paths) {
        if (pts.length < 2) continue
        ctx.beginPath()
        ctx.strokeStyle = 'rgba(246,201,69,0.65)'
        ctx.lineWidth = Math.max(1.5, w / 640)
        ctx.moveTo(pts[0][0], pts[0][1])
        for (let i = 1; i < pts.length; i += 1) ctx.lineTo(pts[i][0], pts[i][1])
        ctx.stroke()
      }
    }

    if (!showBoxes) return
    const lw = Math.max(2, Math.round(w / 480))
    ctx.font = `${Math.max(11, Math.round(w / 90))}px ui-sans-serif, system-ui, sans-serif`
    ctx.textBaseline = 'top'
    // 远端一群人挤在一起时，全标 ID 会糊成一片：只给够大的框标号，最多 10 个
    const boxes = frames[idx].b
    const labeled = new Set<number>()
    if (showIds) {
      const byArea = boxes
        .map((b, i) => ({ i, area: (b[5] - b[3]) * (b[6] - b[4]) }))
        .sort((a, b) => b.area - a.area)
      for (const { i } of byArea) {
        if (labeled.size >= 10) break
        if (boxes[i][1] !== 32 && boxes[i][6] - boxes[i][4] < 46) continue
        labeled.add(i)
      }
    }
    boxes.forEach((b, i) => {
      const [, cls, conf, x1, y1, x2, y2] = b
      const isBall = cls === 32
      const color = isBall ? BALL_COLOR : PERSON_COLOR
      ctx.strokeStyle = color
      ctx.lineWidth = lw
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
      if (!showIds || !labeled.has(i)) return
      const label = isBall
        ? `球 ${(conf * 100).toFixed(0)}%`
        : `#${b[0] ?? '—'} ${(conf * 100).toFixed(0)}%`
      const tw = ctx.measureText(label).width + 8
      const th = Math.max(14, Math.round(w / 70))
      const ty = Math.max(0, y1 - th)
      ctx.fillStyle = isBall ? 'rgba(255,122,162,0.9)' : 'rgba(246,201,69,0.92)'
      ctx.fillRect(x1, ty, tw, th)
      ctx.fillStyle = '#1a1a1a'
      ctx.fillText(label, x1 + 4, ty + 1)
    })
  }, [showBoxes, showIds, showTrails])

  useEffect(() => {
    let raf = 0
    const tick = () => {
      draw()
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [draw])

  const m = summary.data?.summary ?? null
  const kpi = [
    {
      label: pick(lang, '视频', 'Videos'),
      value: fmtNum(overview.data?.videos.total ?? items.length),
      sub: pick(lang, `已完成 ${overview.data?.videos.by_status.done ?? 0}`, `${overview.data?.videos.by_status.done ?? 0} done`),
    },
    {
      label: pick(lang, '平均人数/帧', 'Persons / frame'),
      value: m ? fmtNum(m.person.per_frame_mean, 1) : '—',
      sub: m ? pick(lang, `最多 ${m.person.per_frame_max}`, `max ${m.person.per_frame_max}`) : undefined,
    },
    {
      label: pick(lang, '唯一 ID', 'Unique IDs'),
      value: m ? fmtNum(m.tracking.unique_ids) : '—',
      sub: m ? pick(lang, `碎裂 ${m.tracking.fragmentation ?? '—'}`, `frag ${m.tracking.fragmentation ?? '—'}`) : undefined,
    },
    {
      label: pick(lang, '球检出覆盖率', 'Ball coverage'),
      value: m ? `${m.ball.frames_with_ball_pct}%` : '—',
      sub: m ? pick(lang, `最长连续 ${m.ball.longest_consecutive_run} 帧`, `${m.ball.longest_consecutive_run}-frame streak`) : undefined,
    },
  ]

  return (
    <PageShell
      title={pick(lang, '视频分析', 'Video analysis')}
      subtitle={pick(
        lang,
        'YOLOv8 检测 + ByteTrack 跟踪 · 处理在本地 .venv-vision 跑，网页只排队与展示',
        'YOLOv8 detection + ByteTrack · processing runs locally in .venv-vision',
      )}
      activePath="/vision"
      right={
        <button
          type="button"
          onClick={() => {
            overview.reload()
            videos.reload()
            clearApiCache('vision-tracks')
            clearApiCache('vision-summary')
          }}
          className="glass-soft flex h-9 w-9 items-center justify-center rounded-full transition-transform duration-300 hover:scale-110 active:scale-90"
          title={pick(lang, '刷新', 'Refresh')}
        >
          <RefreshCw size={15} />
        </button>
      }
    >
      <KpiStrip items={kpi} />

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* 播放器 */}
        <div className="xl:col-span-2">
          <SectionCard
            title={selected ? selected.name : pick(lang, '播放器', 'Player')}
            hint={
              selected
                ? `${fmtDuration(selected.duration)} · ${selected.fps ? `${selected.fps} fps` : '—'} · ${
                    selected.width ? `${selected.width}×${selected.height}` : '—'
                  } · ${fmtSize(selected.size_bytes)}`
                : pick(lang, '先上传一段视频，或从右侧列表里选一个', 'Upload a clip or pick one from the list')
            }
            right={
              selected ? (
                <div className="flex items-center gap-2">
                  <label className="t-2 flex items-center gap-1.5 text-[11px]">
                    <input type="checkbox" checked={showBoxes} onChange={(e) => setShowBoxes(e.target.checked)} />
                    {pick(lang, '框', 'boxes')}
                  </label>
                  <label className="t-2 flex items-center gap-1.5 text-[11px]">
                    <input type="checkbox" checked={showIds} onChange={(e) => setShowIds(e.target.checked)} />
                    {pick(lang, '标签', 'labels')}
                  </label>
                  <label className="t-2 flex items-center gap-1.5 text-[11px]">
                    <input type="checkbox" checked={showTrails} onChange={(e) => setShowTrails(e.target.checked)} />
                    {pick(lang, '轨迹', 'trails')}
                  </label>
                </div>
              ) : null
            }
          >
            {selected ? (
              <div className="relative overflow-hidden rounded-[18px] bg-black">
                <video
                  ref={videoRef}
                  key={selected.video_id}
                  src={api.visionStreamUrl(selected.video_id)}
                  controls
                  playsInline
                  preload="metadata"
                  className="block h-auto max-h-[62vh] w-full"
                />
                <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
              </div>
            ) : (
              <EmptyState text={pick(lang, '还没有视频。上传一段 30~120 秒、单一固定机位的比赛片段。', 'No video yet. Upload a 30–120 s single-camera clip.')} />
            )}
            {selected && doneJobId ? (
              <p className="t-3 mt-2 text-[11px] leading-relaxed">
                {tracks.data
                  ? pick(
                      lang,
                      `任务 #${doneJobId} · 抽样 ${tracks.data.frames.length} 帧 / ${tracks.data.boxes} 个框（每 ${tracks.data.step} 帧存一条）`,
                      `Job #${doneJobId} · ${tracks.data.frames.length} sampled frames / ${tracks.data.boxes} boxes`,
                    )
                  : pick(lang, '轨迹加载中…', 'Loading tracks…')}
              </p>
            ) : null}
            {selected && !doneJobId ? (
              <p className="t-3 mt-2 text-[11px]">
                {pick(lang, '这个视频还没有处理结果，右侧点「开始处理」。', 'No results yet — hit “Start processing”.')}
              </p>
            ) : null}
          </SectionCard>

          {/* 指标 */}
          <div className="mt-4">
            <SectionCard
              title={pick(lang, '指标', 'Metrics')}
              hint={pick(
                lang,
                '没有人工标注真值，所以这里没有召回率/mAP —— 它证明的是管线跑通，不是模型精度',
                'No ground truth labels: no recall/mAP here — this proves the pipeline, not accuracy',
              )}
            >
              {summary.loading ? (
                <CardSkeleton rows={3} />
              ) : summary.error ? (
                <ErrorState text={summary.error} />
              ) : !m ? (
                <EmptyState text={pick(lang, '还没有指标：处理完成后出现', 'No metrics yet — run processing first')} />
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      [pick(lang, '处理帧数', 'Frames'), fmtNum(m.frames_processed)],
                      [pick(lang, '人数/帧', 'Persons/frame'), fmtNum(m.person.per_frame_mean, 1)],
                      [pick(lang, '唯一 ID', 'Unique IDs'), fmtNum(m.tracking.unique_ids)],
                      [pick(lang, 'ID 碎裂', 'Fragmentation'), `${m.tracking.fragmentation ?? '—'}`],
                    ].map(([label, value]) => (
                      <div key={label} className="glass-soft rounded-[16px] px-3 py-2">
                        <div className="t-3 text-[10.5px]">{label}</div>
                        <div className="t-1 mt-0.5 text-[16px] font-semibold tabular-nums">{value}</div>
                      </div>
                    ))}
                  </div>

                  <div>
                    <div className="t-2 mb-1.5 text-[11px]">
                      {pick(lang, '框尺寸分布（远 / 中 / 近）', 'Box size buckets (far / mid / near)')}
                    </div>
                    {(['far', 'mid', 'near'] as const).map((k) => (
                      <div key={k} className="mb-1.5 flex items-center gap-2">
                        <span className="t-3 w-14 text-[10.5px] tabular-nums">
                          {k === 'far' ? `<${m.box_height_px.cutoffs_px.far_below}px` : k === 'mid' ? `${m.box_height_px.cutoffs_px.far_below}~${m.box_height_px.cutoffs_px.mid_below}px` : `>${m.box_height_px.cutoffs_px.mid_below}px`}
                        </span>
                        <div className="flex-1">
                          <Bar value={m.box_height_px.buckets_pct[k] ?? 0} tone={k === 'far' ? 'pink' : k === 'mid' ? 'yellow' : 'green'} />
                        </div>
                        <span className="t-2 w-20 text-right text-[10.5px] tabular-nums">
                          {m.box_height_px.buckets[k]} · {(m.box_height_px.buckets_pct[k] ?? 0).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-1">
                    {(summary.data?.verdict ?? []).map((v) => (
                      <div key={v.text} className="glass-soft flex items-center gap-2 rounded-[14px] px-2.5 py-1.5">
                        <Pill tone={v.mark === 'OK  ' ? 'green' : v.mark === '待看' ? 'yellow' : 'pink'}>{v.mark.trim() || '?'}</Pill>
                        <span className="t-2 text-[11.5px]">{v.text}</span>
                      </div>
                    ))}
                  </div>

                  {m.speed ? (
                    <p className="t-3 text-[10.5px] tabular-nums">
                      {pick(lang, '处理速度', 'Throughput')}: {m.speed.fps_processed} fps · {m.speed.elapsed_sec}s
                    </p>
                  ) : null}
                  <ul className="t-3 space-y-1 text-[10.5px] leading-relaxed">
                    {(m.notes ?? []).map((n) => (
                      <li key={n}>· {n}</li>
                    ))}
                  </ul>
                </div>
              )}
            </SectionCard>
          </div>
        </div>

        {/* 右列：库 / 上传 / 处理 */}
        <div className="space-y-4">
          <SectionCard
            title={pick(lang, '视频库', 'Library')}
            hint={pick(lang, '点一行切换左侧播放器', 'Click a row to show it on the left')}
          >
            {videos.loading && !items.length ? (
              <CardSkeleton rows={4} />
            ) : videos.error ? (
              <ErrorState text={videos.error} />
            ) : !items.length ? (
              <EmptyState text={pick(lang, '还没有上传过视频', 'No videos uploaded yet')} />
            ) : (
              <div className="space-y-2">
                {items.map((v) => (
                  <button
                    key={v.video_id}
                    type="button"
                    onClick={() => setSelectedId(v.video_id)}
                    className={`glass-soft anim-in flex w-full items-center gap-2.5 rounded-[16px] px-3 py-2 text-left transition-transform duration-200 hover:scale-[1.01] ${
                      selected?.video_id === v.video_id ? 'ring-1 ring-white/25' : ''
                    }`}
                  >
                    <VideoIcon size={14} className="t-3 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="t-1 block truncate text-[12px] font-medium">{v.name}</span>
                      <span className="t-3 block text-[10px] tabular-nums">
                        {fmtDuration(v.duration)} · {fmtSize(v.size_bytes)}
                        {v.brief ? ` · ${fmtNum(v.brief.persons_per_frame, 1)} 人/帧` : ''}
                      </span>
                    </span>
                    <Pill tone={STATUS_TONE[v.status] ?? 'muted'}>{statusText(lang, v.status)}</Pill>
                  </button>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title={pick(lang, '上传 / 处理', 'Upload & process')}>
            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/quicktime,video/x-matroska,video/x-msvideo,video/webm,.mp4,.mov,.mkv,.avi,.flv,.m4v"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onUpload(f)
              }}
            />
            <button
              type="button"
              disabled={busy === 'upload'}
              onClick={() => fileRef.current?.click()}
              className="glass-soft t-1 flex w-full items-center justify-center gap-2 rounded-[16px] px-3 py-2.5 text-[12px] font-semibold transition-transform duration-200 hover:scale-[1.01] disabled:opacity-50"
            >
              <Upload size={14} />
              {busy === 'upload'
                ? pick(lang, '上传中…', 'Uploading…')
                : pick(lang, '选择视频并上传', 'Choose a clip')}
            </button>
            <p className="t-3 mt-1.5 text-[10.5px] leading-relaxed">
              {pick(
                lang,
                `上限 ${(overview.data ? overview.data.defaults.max_bytes / 1024 / 1024 : 300).toFixed(0)} MB · 支持 mp4 / mov / mkv / avi / webm · 建议 30~120 秒、单一固定机位`,
                `Max ${(overview.data ? overview.data.defaults.max_bytes / 1024 / 1024 : 300).toFixed(0)} MB · mp4/mov/mkv/avi/webm · 30–120 s, single camera`,
              )}
            </p>

            <div className="mt-3 flex items-center gap-2">
              <span className="t-3 text-[11px]">{pick(lang, '抽样间隔', 'Sample every')}</span>
              <select
                value={step}
                onChange={(e) => setStep(Number(e.target.value))}
                className="glass-soft t-1 rounded-full px-2.5 py-1 text-[11px] outline-none"
              >
                {[1, 2, 5, 10, 20].map((n) => (
                  <option key={n} value={n}>
                    {n} {pick(lang, '帧', 'frames')}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              disabled={!currentId || busy === 'process' || Boolean(running)}
              onClick={() => void onProcess()}
              className="t-1 mt-2 flex w-full items-center justify-center gap-2 rounded-[16px] bg-[#F6C945] px-3 py-2.5 text-[12px] font-bold text-[#1a1a1a] transition-transform duration-200 hover:scale-[1.01] disabled:opacity-40"
            >
              <Play size={14} />
              {running
                ? pick(lang, '任务进行中…', 'Job in progress…')
                : pick(lang, '开始处理', 'Start processing')}
            </button>

            {job && (running || job.status === 'failed' || job.status === 'done') ? (
              <div className="mt-3">
                <div className="t-2 mb-1 flex items-center justify-between text-[11px] tabular-nums">
                  <span>
                    #{job.job_id} · {statusText(lang, job.status)}
                  </span>
                  <span>
                    {job.frames_done}/{job.frames_total ?? '—'}
                  </span>
                </div>
                <Bar value={job.progress} tone={job.status === 'failed' ? 'pink' : 'yellow'} />
                {job.message ? <p className="t-3 mt-1 text-[10.5px]">{job.message}</p> : null}
                {job.error ? <p className="mt-1 text-[10.5px] text-[#FF7AA2]">{job.error}</p> : null}
                {running ? (
                  <button type="button" onClick={() => void onCancel()} className="t-3 mt-1.5 text-[10.5px] underline">
                    {pick(lang, '取消任务', 'Cancel job')}
                  </button>
                ) : null}
                {job.overlay && selected ? (
                  <a href={api.visionOverlayUrl(selected.video_id)} className="t-3 mt-1.5 block text-[10.5px] underline" download>
                    {pick(lang, '下载带框视频', 'Download overlay video')}
                  </a>
                ) : null}
              </div>
            ) : null}

            {selected ? (
              <button
                type="button"
                disabled={busy === 'delete' || Boolean(running)}
                onClick={() => void onDelete(selected)}
                className="t-3 mt-3 flex items-center gap-1.5 text-[10.5px] underline disabled:opacity-40"
              >
                <Trash2 size={12} />
                {pick(lang, '删除这个视频', 'Delete this video')}
              </button>
            ) : null}
          </SectionCard>

          <SectionCard title={pick(lang, '怎么跑处理', 'How processing runs')}>
            <div className="t-2 space-y-2 text-[11px] leading-relaxed">
              <p>
                {pick(
                  lang,
                  '网页只负责排队；推理要 torch + ultralytics（约 2.5 GB），在本地独立环境里由处理进程领取。',
                  'The web app only queues jobs; inference (torch + ultralytics, ~2.5 GB) runs in a separate local env.',
                )}
              </p>
              <ol className="t-3 space-y-1 text-[10.5px]">
                <li>
                  1. {pick(lang, '装依赖（只需一次）', 'Install deps (once)')}:
                  <code className="glass-soft ml-1 rounded px-1">powershell -ExecutionPolicy Bypass -File scripts\vision_setup.ps1</code>
                </li>
                <li>
                  2. {pick(lang, '跑处理进程（在仓库根目录）', 'Run the worker (repo root)')}:
                  <code className="glass-soft ml-1 rounded px-1">.venv-vision\Scripts\python.exe scripts\run_vision_jobs.py</code>
                </li>
                <li>3. {pick(lang, '它会自己领走这个页面上排的任务，进度实时显示。', 'It picks up queued jobs and updates progress live.')}</li>
              </ol>
              <div className="glass-soft flex items-center justify-between gap-2 rounded-[14px] px-2.5 py-1.5">
                <span>{pick(lang, '处理进程', 'Worker')}</span>
                <Pill tone={worker?.online ? 'green' : 'muted'}>
                  {worker?.online
                    ? `${pick(lang, '在线', 'online')}${worker.heartbeat_age != null ? ` · ${Math.round(worker.heartbeat_age)}s` : ''}`
                    : pick(lang, '离线', 'offline')}
                </Pill>
              </div>
              <div className="glass-soft flex items-center justify-between gap-2 rounded-[14px] px-2.5 py-1.5">
                <span>{pick(lang, '显卡', 'GPU')}</span>
                <span className="t-2 max-w-[62%] truncate text-right text-[10.5px]" title={worker?.gpu ?? ''}>
                  {worker?.gpu ?? '—'}
                </span>
              </div>
              <div className="glass-soft flex items-center justify-between gap-2 rounded-[14px] px-2.5 py-1.5">
                <span>{pick(lang, '依赖版本', 'Deps')}</span>
                <span className="t-2 max-w-[62%] truncate text-right text-[10.5px]">{worker?.deps ?? '—'}</span>
              </div>
              <p className="t-3 text-[10.5px] leading-relaxed">
                {pick(
                  lang,
                  '网页进程不装 torch（云主机 2 GiB 装不下）：它只排队与展示，上面三行是处理进程自报的状态。',
                  'The web process has no torch (it does not fit on a 2 GiB host): it only queues and displays; the rows above are self-reported by the worker.',
                )}
              </p>
            </div>
          </SectionCard>
        </div>
      </div>

      {actionError ? (
        <div className="mt-4">
          <ErrorState text={actionError} />
        </div>
      ) : null}
      {notice ? <p className="t-3 mt-3 text-[11px]">{notice}</p> : null}
    </PageShell>
  )
}
