import { useState } from 'react'
import type { FrameRef } from '../api'

/**
 * 구간의 화면을 크게 한 장 보여 주고, 화면이 여러 장이면 아래에 썸네일 줄을 둡니다.
 * 썸네일을 누르면 큰 화면이 바뀌고, 시각 버튼을 누르면 영상이 그 화면 시점으로 이동합니다.
 */
export function FrameGallery({
  frames,
  fallbackUrl,
  title,
  onSeek,
}: {
  frames: FrameRef[]
  /** ``frames``가 비었을 때 보여 줄 대표 화면 */
  fallbackUrl: string | null
  title: string
  onSeek: (seconds: number) => void
}) {
  const [selected, setSelected] = useState(0)
  const frame = frames[Math.min(selected, frames.length - 1)]
  const url = frame?.url ?? fallbackUrl
  if (!url) return null

  return (
    <figure className="frame-gallery">
      <img src={url} alt={`${title} 화면${frame ? ` (${frame.label})` : ''}`} loading="lazy" />
      {frames.length > 1 && (
        <>
          <figcaption>
            <span>
              화면 {selected + 1}/{frames.length}
            </span>
            <button type="button" className="frame-seek" onClick={() => onSeek(frame.time)}>
              ▶ {frame.label}
            </button>
          </figcaption>
          <div className="frame-thumbs">
            {frames.map((item, position) => (
              <button
                type="button"
                key={item.url}
                className={position === selected ? 'on' : undefined}
                onClick={() => setSelected(position)}
                aria-label={`${item.label} 화면 보기`}
                aria-pressed={position === selected}
              >
                <img src={item.url} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </>
      )}
    </figure>
  )
}

/** 챕터 안에서 바뀐 화면들을 작은 썸네일 줄로 보여 줍니다. 누르면 그 화면 시점부터 재생합니다. */
export function FrameStrip({
  frames,
  title,
  onSeek,
}: {
  frames: FrameRef[]
  title: string
  onSeek: (seconds: number) => void
}) {
  // 한 장뿐이면 챕터 머리의 썸네일과 같으므로 따로 보여 주지 않습니다.
  if (frames.length < 2) return null
  return (
    <div className="frame-strip" aria-label={`${title} 화면 ${frames.length}장`}>
      {frames.map((frame) => (
        <button type="button" key={frame.url} onClick={() => onSeek(frame.time)} title={`${frame.label}부터 재생`}>
          <img src={frame.url} alt={`${title} ${frame.label} 화면`} loading="lazy" />
          <span>{frame.label}</span>
        </button>
      ))}
    </div>
  )
}
