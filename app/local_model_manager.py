"""Select only inside the single inference executor, never in request threads."""
from configs.local_models import get_profile, require_downloaded, repo_path

class LocalModelManager:
    def __init__(self, original_runner):
        self.original = original_runner
        self.active_id = None
        self.active_runner = original_runner

    def _runner_for(self, model_id):
        if model_id == self.active_id:
            return self.active_runner
        profile = get_profile(model_id)
        require_downloaded(model_id)
        self.active_runner.summary_service.unload_llm()
        self.active_runner.summary_service.unload_vlm()
        # Release even if construction fails, so no stale profile can be reused.
        self.active_id = None
        from services.summary_service import SummaryService
        from app.inference_jobs import InferenceJobRunner
        if model_id == "legacy-qwen":
            from models.llm_loader import LLMLoader, LLMConfig
            from models.vlm_loader import VLMLoader, VLMConfig
            service = SummaryService(
                LLMLoader(LLMConfig(model_path=str(repo_path(profile.repos[0])))),
                VLMLoader(VLMConfig(model_path=str(repo_path(profile.repos[1])))))
        else:
            if profile.runtime == "minicpm":
                from models.minicpm_loader import MiniCPMLoader
                loader = MiniCPMLoader(model_id)
            else:
                from models.multimodal_loader import MultimodalLoader
                loader = MultimodalLoader(model_id)
            service = SummaryService(loader, loader)
        self.active_runner = InferenceJobRunner(service, self.original.job_store, self.original.logger,
            keep_llm_loaded=model_id != "legacy-qwen", keep_vlm_loaded=model_id != "legacy-qwen")
        self.active_id = model_id
        return self.active_runner

    def run(self, model_id, method, job_id, *args):
        try:
            if model_id is None:
                # Compatibility for old clients. Explicit profiles always remain local.
                if self.active_runner is not self.original:
                    self.active_runner.summary_service.unload_llm()
                    self.active_runner.summary_service.unload_vlm()
                self.active_runner = self.original
                self.active_id = None
                runner = self.original
            else:
                runner = self._runner_for(model_id)
            getattr(runner, method)(job_id, *args)
        except Exception as error:
            self.original.logger.exception("모델 선택 실패: %s", model_id)
            self.original.job_store.update(job_id, status="failed", message="로컬 모델 준비 실패", error=str(error))
