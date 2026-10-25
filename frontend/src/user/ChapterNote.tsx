import { useMemo, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { NoteChapter, NoteOutline } from '../api'
import { FrameGallery, FrameStrip } from '../components/FrameGallery'

/** 강의노트를 챕터 플레이어로 보여 줍니다. 맨 위 3줄 요약·키워드, 영상과 챕터 목록, 화면 속 자료, 정리 순서입니다. */
export function ChapterNote({ outline, videoUrl }: { outline: NoteOutline; videoUrl: string | null }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const chapterRefs = useRef<(HTMLElement | null)[]>([])
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playing, setPlaying] = useState(false)

  // 시간 순서로 놓고, 시간을 모르는 챕터는 원래 순서대로 맨 뒤에 둡니다.
  const chapters = useMemo(
    () => [...outline.chapters].sort((a, b) => (a.start ?? Infinity) - (b.start ?? Infinity)),
    [outline.chapters],
  )
  // 재생을 시작하기 전에는 어느 챕터도 강조하지 않습니다.
  const current = playing || time > 0 ? currentChapter(chapters, time) : -1
  // 영상 길이를 아직 모르면 마지막 챕터 끝을 전체 길이로 씁니다(재생 막대가 비어 보이지 않게).
  const total = Math.max(
    duration,
    ...chapters.map((chapter) => (chapter.start === null ? 0 : (chapter.end ?? chapter.start + 1))),
  )

  const seek = (seconds: number) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    void video.play()
    if (window.matchMedia('(max-width: 960px)').matches) video.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const openChapter = (position: number) => {
    const start = chapters[position].start
    if (start !== null) seek(start)
    chapterRefs.current[position]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  return (
    <div className="u-cn">
      {outline.notices.length > 0 && (
        <section className="u-cn-notice" aria-label="공지">
          <p className="u-cn-label">📢 공지</p>
          <ul>
            {outline.notices.map((notice) => (
              <li key={notice}>{notice}</li>
            ))}
          </ul>
        </section>
      )}

      {(outline.key_points.length > 0 || outline.keywords.length > 0) && (
        <section className="u-cn-tldr">
          {outline.key_points.length > 0 && (
            <div>
              <p className="u-cn-label">3줄 요약</p>
              <ol className="u-cn-points">
                {outline.key_points.slice(0, 3).map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ol>
            </div>
          )}
          {outline.keywords.length > 0 && (
            <div className="u-cn-keywords">
              <p className="u-cn-label">키워드</p>
              <div>
                {outline.keywords.map((keyword) => (
                  <span className="u-cn-chip" key={keyword}>
                    {keyword}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {outline.emphasis.length > 0 && (
        <section className="u-cn-emphasis" aria-label="강사가 강조한 내용">
          <p className="u-cn-label">⭐ 강사가 강조한 내용</p>
          <ul>
            {outline.emphasis.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="u-cn-grid">
        <aside className="u-cn-player">
          {videoUrl ? (
            <video
              ref={videoRef}
              src={videoUrl}
              controls
              preload="metadata"
              onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
              onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
            />
          ) : (
            <div className="u-video-missing">원본 영상을 찾을 수 없어요.</div>
          )}
          <ChapterBar chapters={chapters} total={total} time={time} current={current} onPick={openChapter} />
          <p className="u-cn-now">
            {current >= 0 ? (
              <>
                <span className="u-cn-live">{playing ? '재생 중' : '일시정지'}</span> {chapters[current].index}.{' '}
                {chapters[current].title}
              </>
            ) : (
              <span className="u-muted">챕터를 누르면 그 장면부터 재생돼요.</span>
            )}
          </p>
        </aside>

        <ol className="u-cn-chapters">
          {chapters.map((chapter, position) => (
            <li
              key={`${chapter.index}-${chapter.start}`}
              ref={(element) => {
                chapterRefs.current[position] = element
              }}
              className={`u-cn-chapter${position === current ? ' on' : ''}`}
            >
              <ChapterCard
                chapter={chapter}
                status={position === current ? (playing ? '재생 중' : '일시정지') : null}
                onPlay={chapter.start === null ? null : () => seek(chapter.start ?? 0)}
                onSeek={seek}
              />
            </li>
          ))}
        </ol>
      </div>

      {outline.visuals.length > 0 && (
        <section className="u-cn-section">
          <h2>📊 화면 속 자료</h2>
          <div className="u-cn-visuals">
            {outline.visuals.map((visual) => (
              <article className="u-cn-visual" key={`${visual.index}-${visual.start}`}>
                {(visual.image_url || visual.frames.length > 0) && (
                  <FrameGallery frames={visual.frames} fallbackUrl={visual.image_url} title={visual.title} onSeek={seek} />
                )}
                <div>
                  <div className="u-cn-visual-head">
                    {visual.kind && visual.kind !== visual.title && <span className="u-cn-type">{visual.kind}</span>}
                    <strong>{visual.title}</strong>
                    {visual.start !== null ? (
                      <button className="u-cn-time" onClick={() => seek(visual.start ?? 0)}>
                        ▶ {visual.label}
                      </button>
                    ) : (
                      <span className="u-cn-time none">{visual.label}</span>
                    )}
                  </div>
                  <div className="u-cn-md">
                    <Markdown remarkPlugins={[remarkGfm]}>{visual.text}</Markdown>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {outline.terms.length > 0 && (
        <section className="u-cn-section">
          <h2>📘 핵심 용어</h2>
          <dl className="u-cn-terms">
            {outline.terms.map((term) => (
              <div key={term.term}>
                <dt>{term.term}</dt>
                {term.definition && <dd>{term.definition}</dd>}
              </div>
            ))}
          </dl>
        </section>
      )}

      {outline.conclusion.length > 0 && (
        <section className="u-cn-section u-cn-conclusion">
          <h2>✅ 정리</h2>
          <ul>
            {outline.conclusion.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      {outline.extras.length > 0 && (
        <section className="u-cn-section u-cn-md">
          {outline.extras.map((text, position) => (
            <Markdown key={position} remarkPlugins={[remarkGfm]}>
              {text}
            </Markdown>
          ))}
        </section>
      )}
    </div>
  )
}

/** 영상 아래 챕터 막대입니다. 칸 하나가 챕터 하나(다음 챕터 시작까지)이며 누르면 그 챕터로 이동합니다.
 * 시간을 모르는 챕터(목록 맨 뒤)는 막대에 넣지 않습니다. */
function ChapterBar({
  chapters,
  total,
  time,
  current,
  onPick,
}: {
  chapters: NoteChapter[]
  total: number
  time: number
  current: number
  onPick: (position: number) => void
}) {
  if (total <= 0) return null
  return (
    <div className="u-cn-bar" role="group" aria-label="챕터 이동">
      {chapters.map((chapter, position) => {
        const start = chapter.start
        if (start === null) return null
        const end = chapters[position + 1]?.start ?? total
        const left = (start / total) * 100
        const width = Math.max(((end - start) / total) * 100, 1.5)
        const filled = Math.min(Math.max((time - start) / (end - start || 1), 0), 1) * 100
        return (
          <button
            key={`${chapter.index}-${chapter.start}`}
            className={`u-cn-seg${position === current ? ' on' : ''}`}
            style={{ left: `${left}%`, width: `${width}%` }}
            title={`${chapter.index}. ${chapter.title} (${chapter.label})`}
            aria-label={`${chapter.index}. ${chapter.title}, ${chapter.label}`}
            onClick={() => onPick(position)}
          >
            <span style={{ width: `${filled}%` }} />
          </button>
        )
      })}
    </div>
  )
}

function ChapterCard({
  chapter,
  status,
  onPlay,
  onSeek,
}: {
  chapter: NoteChapter
  status: string | null
  /** 시간을 모르는 챕터는 null이며, 이때 제목 줄은 재생 버튼이 아닙니다. */
  onPlay: (() => void) | null
  onSeek: (seconds: number) => void
}) {
  const head = (
    <>
      {chapter.thumb_url ? (
        <img className="u-cn-thumb" src={chapter.thumb_url} alt="" loading="lazy" />
      ) : (
        <span className="u-cn-thumb empty">{chapter.index}</span>
      )}
      <span className="u-cn-chapter-title">
        <span className={`u-cn-time${onPlay ? '' : ' none'}`}>
          {onPlay ? '▶ ' : ''}
          {chapter.label}
        </span>
        <strong>
          {chapter.index}. {chapter.title}
        </strong>
      </span>
      {status && <span className="u-cn-live">{status}</span>}
    </>
  )
  return (
    <>
      {onPlay ? (
        <button className="u-cn-chapter-head" onClick={onPlay} title="이 장면부터 재생">
          {head}
        </button>
      ) : (
        <div className="u-cn-chapter-head static">{head}</div>
      )}
      <FrameStrip frames={chapter.frames} title={chapter.title} onSeek={onSeek} />
      {chapter.points.length > 0 && (
        <ul className="u-cn-chapter-points">
          {chapter.points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      )}
      {chapter.screen_notes.length > 0 && (
        <div className="u-cn-screen">
          <span className="u-cn-screen-label">📺 화면에서 확인</span>
          {chapter.screen_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      )}
    </>
  )
}

/** 지금 재생 위치가 속한 챕터(시작 시각이 지난 마지막 챕터)의 위치입니다. 첫 챕터 전이면 -1. */
function currentChapter(chapters: NoteChapter[], time: number) {
  let found = -1
  chapters.forEach((chapter, position) => {
    if (chapter.start !== null && chapter.start <= time + 0.25) found = position
  })
  return found
}
