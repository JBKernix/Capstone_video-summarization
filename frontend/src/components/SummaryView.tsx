import { useRef } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { StructuredSummary, SummaryBlock, SummaryContent, SummaryResult } from '../api'
import { FrameGallery } from './FrameGallery'

export type Seek = (seconds: number) => void

function Md({ text }: { text: string }) {
  return <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
}

/** 원본 영상과 최종 요약 결과를 나란히 표시합니다. 타임라인 뱃지를 누르면 영상이 그 지점으로 이동합니다. */
export function SummaryView({ result }: { result: SummaryResult }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const seek: Seek = (seconds) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    void video.play()
    video.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  return (
    <div className="grid-result">
      <div className="card">
        <h2>원본 영상</h2>
        {result.video_url ? (
          <video ref={videoRef} src={result.video_url} controls preload="metadata" />
        ) : (
          <div className="notice warning">표시할 영상을 찾을 수 없습니다.</div>
        )}
      </div>
      <div className="card">
        <h2>요약 결과</h2>
        <div className="summary-scroll">
          <SummaryBody result={result} seek={seek} />
        </div>
      </div>
    </div>
  )
}

/** 요약 본문만 그립니다. 사용자용 강의노트 화면도 이 컴포넌트를 씁니다. */
export function SummaryBody({ result, seek }: { result: SummaryContent; seek: Seek }) {
  return (
    <>
      {result.mode === 'blocks' && <Blocks blocks={result.blocks} seek={seek} />}
      {result.mode === 'structured' && <Structured summary={result.summary} />}
      {result.mode === 'raw' && <pre className="log">{JSON.stringify(result.data, null, 2)}</pre>}
    </>
  )
}

function Blocks({ blocks, seek }: { blocks: SummaryBlock[]; seek: Seek }) {
  return (
    <>
      {blocks.map((block, blockIndex) => {
        if (block.type === 'markdown') return <Md key={blockIndex} text={block.text} />
        return (
          <section key={blockIndex}>
            <h2>{block.heading}</h2>
            {block.items.map((item, itemIndex) => {
              if (item.type === 'markdown') return <Md key={itemIndex} text={item.text} />
              return (
                <div className="item-card" key={itemIndex}>
                  <div className="row">
                    <strong>
                      {item.index}. {item.title}
                    </strong>
                    <span
                      className="timeline-badge"
                      role="button"
                      tabIndex={0}
                      title="이 구간부터 영상 재생"
                      onClick={() => seek(item.start)}
                      onKeyDown={(event) => event.key === 'Enter' && seek(item.start)}
                    >
                      ▶ {item.label}
                    </span>
                  </div>
                  {block.show_images ? (
                    <div className="with-image">
                      <div>
                        {item.image_url || item.frames.length > 0 ? (
                          <FrameGallery
                            frames={item.frames}
                            fallbackUrl={item.image_url}
                            title={item.title}
                            onSeek={seek}
                          />
                        ) : (
                          <p className="caption">해당 구간 화면을 찾을 수 없습니다.</p>
                        )}
                      </div>
                      <div>
                        <Md text={item.text} />
                      </div>
                    </div>
                  ) : (
                    <Md text={item.text} />
                  )}
                </div>
              )
            })}
          </section>
        )
      })}
    </>
  )
}

function Structured({ summary }: { summary: StructuredSummary }) {
  return (
    <>
      <h2>{summary.title || '영상 요약'}</h2>
      {summary.main_topic && (
        <div className="summary-box">
          <h3>핵심 주제</h3>
          <p>{summary.main_topic}</p>
        </div>
      )}
      {summary.keywords && summary.keywords.length > 0 && (
        <>
          <h3>키워드</h3>
          <div>
            {summary.keywords.map((keyword) => (
              <span className="keyword" key={keyword}>
                {keyword}
              </span>
            ))}
          </div>
        </>
      )}
      {summary.topics.length > 0 && (
        <>
          <h3>주제별 요약</h3>
          {summary.topics.map((topic, index) => (
            <details className="topic" open key={index}>
              <summary>
                {`${index + 1}. ${topic.title ?? `주제 ${index + 1}`} ${topic.timeline ?? ''}`.trim()}
              </summary>
              <p>{topic.content}</p>
            </details>
          ))}
        </>
      )}
      {summary.conclusion && (
        <div className="summary-box">
          <h3>종합 결론</h3>
          <p>{summary.conclusion}</p>
        </div>
      )}
    </>
  )
}
