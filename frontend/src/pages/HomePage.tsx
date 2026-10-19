import { Link } from 'react-router-dom'
import { PageTitle } from '../components/Notice'

export function HomePage() {
  return (
    <div className="page">
      <PageTitle sub="새 영상을 업로드해 분석하거나, 저장해 둔 요약 결과를 확인하세요." />
      <div className="grid-2">
        <div className="card">
          <h2>🎥 영상 업로드</h2>
          <p>새 영상을 업로드하거나 유튜브 링크로 영상을 가져와 분석을 시작합니다.</p>
          <Link className="button primary" style={{ width: '100%' }} to="/upload">
            업로드 페이지로 이동
          </Link>
        </div>
        <div className="card">
          <h2>🗂️ 저장된 요약 확인</h2>
          <p>이전에 저장해 둔 영상과 요약 결과를 다시 확인합니다.</p>
          <Link className="button" style={{ width: '100%' }} to="/saved">
            저장된 요약 보기
          </Link>
        </div>
      </div>
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h2>📊 실행 이력</h2>
        <p>실행별 소요 시간, 추출 프레임 수, 오류 로그를 확인하고 CSV로 내려받습니다.</p>
        <Link to="/history">실행 이력과 성능 지표 보기</Link>
      </div>
    </div>
  )
}
