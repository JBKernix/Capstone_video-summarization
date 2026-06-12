# 🎥 멀티모달 기반 영상 요약 시스템

## 🚀 프로젝트 소개

본 프로젝트는 입력 영상으로부터 음성, 이미지 프레임, OCR 텍스트, 시각 정보를 추출하고 이를 구조화하여 영상 내용을 요약하는 멀티모달 기반 영상 분석 시스템입니다.

영상의 음성 정보는 STT를 통해 텍스트로 변환하고, 영상 프레임은 일정 간격 또는 장면 전환 기준으로 추출합니다. 추출된 프레임에서는 OCR 및 이미지 분석을 수행하여 최종적으로 영상 요약에 활용할 수 있는 데이터를 생성합니다.


## ✨ 주요 기능

**지능형 영상 요약**: 전체 요약, 주제별 요약 및 대화 흐름 분석

**하이라이트 타임라인**: 결론 및 의사결정 등 주요 구간 자동 선정 및 타임스탬프 제공

**멀티모달 통합 분석**: 음성 대본과 화면 속 슬라이드/텍스트 정보를 결합한 고정밀 분석

**사용자 친화적 UI**: Streamlit 기반의 간편한 영상 업로드 및 결과 확인 인터페이스

- 영상 파일 입력
- FFmpeg 기반 영상 전처리
- 일정 간격 프레임 추출
- 장면 전환 기반 프레임 추출
- 프레임별 메타데이터 생성
- EasyOCR 기반 이미지 내 텍스트 추출
- 프레임 기반 시각 정보 추출
- STT 결과와 시각 정보 통합
- LLM 요약을 위한 구조화 데이터 생성


## 🧩 시스템 구성

```text
사용자 영상 업로드
        ↓
영상 전처리(음성 추출)
        ↓
STT 변환
        ↓
LLM 요약, 중요 구간 추출
        ↓
중요 구간 프레임 추출
        ↓
프레임 OCR 분석
        ↓
VLM 프레임 분석
        ↓
LLM 최종 요약
        ↓
요약 결과 출력
```


## 👥 팀원 역할

| 이름 | 담당 |
|---|---|
| 함도연 | STT 데이터, AI 모델 조사, VLM/LLM 황경 설정 |
| 김승민 | 영상 전처리(프레임, 오디오 분할), 입출력 UI |
| 정병두 | OCR 데이터, VLM/LLM 모듈 설계 |
| 조윤호 | 입출력 UI |


## 📂 폴더 구조

```text
Capstone_video-summarization/
├── app/              # 실행 애플리케이션 또는 UI 관련 코드
├── configs/          # 설정 파일
├── data/
│   └── input/        # 입력 영상 또는 테스트 데이터
├── docs/             # 문서 자료
├── modules/          # 기능별 모듈 코드
├── scripts/          # 실행 스크립트
├── tests/            # 테스트 코드
├── requirements.txt  # Python 패키지 목록
└── README.md
```


## 🧪 개발 환경

- Language: Python
- 영상 처리: FFmpeg, OpenCV
- OCR: EasyOCR
- 딥러닝 프레임워크: PyTorch
- 개발 환경: VSCode


## 🛠 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/JBKernix/Capstone_video-summarization.git
cd Capstone_video-summarization
```
### 2. 가상환경 생성
```bash
conda create -n capstone_test python=3.11
conda activate capstone_test
```
### 3. 패키지 설치
```bash
pip install -r requirements.txt
```
### 4. FFmpeg 설치 확인
```bash
ffmpeg -version
```


## 📌 현재 개발 상태

- [x] 프로젝트 기본 폴더 구조 구성
- [x] 영상 프레임 추출 모듈 개발
- [x] OCR 추출 모듈 개발
- [x] 시각 정보 구조화 모듈 개발
- [ ] STT 결과 통합
- [ ] LLM 요약 모듈 연동
- [ ] UI 구성
- [ ] 전체 파이프라인 통합


## ▶️ 실행 방법

현재 전체 파이프라인은 개발 중입니다.<br>
기능별 모듈은 `modules/` 폴더에서 관리하며, 실행 스크립트는 `scripts/` 또는 `app/` 폴더에서 관리할 예정입니다.

예시: 
```bash
python scripts/run_pipeline.py
```
