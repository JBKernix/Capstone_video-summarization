"""MiniCPM uses its own Transformers 4.51 environment, isolated from 5.x."""
import base64
import io
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from models.multimodal_loader import MultimodalLoader
from configs.local_models import PROJECT_ROOT, require_downloaded

class MiniCPMLoader(MultimodalLoader):
    def __init__(self, model_id="minicpm-v4.5"):
        super().__init__(model_id)
        self.process = None
        self._log = None

    def _load(self):
        if self.process and self.process.poll() is None and self.model is not None:
            return self.model, self.processor
        self.unload()
        require_downloaded(self.profile.id)
        default = PROJECT_ROOT / ".venv-minicpm" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = Path(os.environ.get("MINICPM_PYTHON", default))
        if not python.is_file():
            raise ValueError("MiniCPM 전용 환경이 없습니다. python scripts/setup_minicpm.py를 먼저 실행하세요.")
        logdir = PROJECT_ROOT / "logs"
        logdir.mkdir(exist_ok=True)
        self._log = (logdir / "minicpm-worker.log").open("a", encoding="utf-8")
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONIOENCODING="utf-8")
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("HF_TOKEN", None)
        self.process = subprocess.Popen([str(python), "-u", str(PROJECT_ROOT / "scripts" / "minicpm_worker.py"), self.config.model_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log, text=True, encoding="utf-8", env=env)
        try:
            self._receive(timeout=600)
        except Exception:
            self.unload()
            raise
        self.model = self.processor = True
        return self.model, self.processor

    def count_prompt_tokens(self, prompt):
        # 토크나이저가 별도 worker 프로세스에 있어 셀 수 없습니다. LLMService가 글자 수로 어림합니다.
        return None

    def _receive(self, timeout=1800):
        output = queue.Queue()
        pipe = self.process.stdout
        def read():
            try:
                output.put(pipe.readline())
            except Exception:
                output.put("")
        threading.Thread(target=read, daemon=True).start()
        try:
            line = output.get(timeout=timeout)
            if not line:
                raise ValueError("MiniCPM worker가 종료되었습니다. 서버 logs/minicpm-worker.log를 확인하세요.")
            response = json.loads(line)
            if "error" in response:
                raise ValueError(response["error"])
            return response
        except (queue.Empty, json.JSONDecodeError) as error:
            self.unload()
            raise ValueError("MiniCPM worker 응답 시간 초과 또는 프로토콜 오류") from error

    def _generate(self, model, processor, prompt, image, max_new_tokens):
        payload = {"prompt": prompt, "max_new_tokens": max_new_tokens}
        if image is not None:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            payload["image"] = base64.b64encode(buffer.getvalue()).decode("ascii")
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            return self._receive()["text"]
        except Exception:
            self.unload()
            raise

    def unload(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    pipe.close()
        if self._log:
            self._log.close()
            self._log = None
        self.model = self.processor = None
