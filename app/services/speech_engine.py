"""Speech-to-Text Transcription Engines (Layer 3).

Supports:
- Local Faster-Whisper (with VAD filter, beam_size=5, word_timestamps=True, condition_on_previous_text=False)
- OpenAI Whisper API
- Deepgram Nova-2 / Nova-3 (with keyword boosting)
- Azure Speech Services (phrase lists stub)

Switchable via STT_ENGINE environment variable.
"""

import io
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any, Optional

from app.core.config import settings
from app.services.speech_audio import preprocess_audio

logger = logging.getLogger("app.services.speech_engine")


@dataclass
class WordConfidence:
    word: str
    start: float
    end: float
    probability: float
    low_confidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class STTResult:
    text: str
    raw_text: str = ""
    words: list[WordConfidence] = field(default_factory=list)
    language: str = "en"
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "raw_text": self.raw_text,
            "words": [w.to_dict() for w in self.words],
            "language": self.language,
            "duration": self.duration,
        }


class BaseSTTEngine(ABC):
    """Abstract base class for all STT providers."""

    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/webm",
        language: str = "en",
        prompt: Optional[str] = None,
        candidate_name: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        """Transcribe audio into text with word confidences."""
        pass


class FasterWhisperEngine(BaseSTTEngine):
    """Local high-performance transcription using faster-whisper (CTranslate2)."""

    def __init__(self):
        self._model = None
        self._model_lock = Lock()
        self.model_name = getattr(settings, "WHISPER_MODEL", None) or os.environ.get("WHISPER_MODEL", "base")
        self.device = getattr(settings, "WHISPER_DEVICE", None) or os.environ.get("WHISPER_DEVICE", "auto")
        self.compute_type = getattr(settings, "WHISPER_COMPUTE_TYPE", None) or os.environ.get("WHISPER_COMPUTE_TYPE", "default")
        self.beam_size = int(getattr(settings, "WHISPER_BEAM_SIZE", 5) or os.environ.get("WHISPER_BEAM_SIZE", "5"))

    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    try:
                        from faster_whisper import WhisperModel

                        logger.info(
                            "Initializing Faster-Whisper model=%r device=%r compute_type=%r",
                            self.model_name,
                            self.device,
                            self.compute_type,
                        )
                        self._model = WhisperModel(
                            self.model_name,
                            device=self.device,
                            compute_type=self.compute_type,
                        )
                    except Exception as exc:
                        logger.error("Failed to load Faster-Whisper model %s: %s", self.model_name, exc)
                        raise
        return self._model

    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/webm",
        language: str = "en",
        prompt: Optional[str] = None,
        candidate_name: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        if not audio_bytes:
            return STTResult(text="", raw_text="")

        model = self._get_model()

        # Convert to 16 kHz mono WAV via Layer 2
        processed_wav, _ = preprocess_audio(audio_bytes, content_type=content_type)
        audio_source = io.BytesIO(processed_wav)

        lang_code = language[:2] if language else "en"

        vad_params = dict(
            min_silence_duration_ms=500,
            threshold=0.45,
        )

        segments, info = model.transcribe(
            audio_source,
            language=lang_code,
            beam_size=self.beam_size,
            initial_prompt=prompt,
            vad_filter=True,
            vad_parameters=vad_params,
            condition_on_previous_text=False,
            word_timestamps=True,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
        )

        full_text_parts = []
        words_list: list[WordConfidence] = []

        for seg in segments:
            full_text_parts.append(seg.text.strip())
            if hasattr(seg, "words") and seg.words:
                for w in seg.words:
                    prob = float(w.probability if hasattr(w, "probability") else 1.0)
                    words_list.append(
                        WordConfidence(
                            word=w.word.strip(),
                            start=round(float(w.start), 3),
                            end=round(float(w.end), 3),
                            probability=round(prob, 3),
                            low_confidence=(prob < 0.70),
                        )
                    )

        raw_text = " ".join(p for p in full_text_parts if p).strip()
        duration = float(getattr(info, "duration", 0.0) or 0.0)

        return STTResult(
            text=raw_text,
            raw_text=raw_text,
            words=words_list,
            language=info.language if hasattr(info, "language") else lang_code,
            duration=round(duration, 2),
        )


class OpenAIWhisperEngine(BaseSTTEngine):
    """Transcription via OpenAI Whisper API."""

    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/webm",
        language: str = "en",
        prompt: Optional[str] = None,
        candidate_name: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        if not audio_bytes:
            return STTResult(text="", raw_text="")

        openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")
        if not openai_key:
            logger.warning("OpenAIWhisperEngine called but OPENAI_API_KEY not set.")
            return STTResult(text="", raw_text="")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            ext = "webm" if "webm" in content_type else "wav"
            buffer = io.BytesIO(audio_bytes)
            buffer.name = f"audio.{ext}"

            kwargs_opts: dict = {
                "model": "whisper-1",
                "file": buffer,
                "language": language[:2] if language else "en",
                "response_format": "verbose_json",
                "timestamp_granularities": ["word"],
            }
            if prompt:
                kwargs_opts["prompt"] = prompt

            res = client.audio.transcriptions.create(**kwargs_opts)
            text = getattr(res, "text", "") or ""
            words_list: list[WordConfidence] = []

            if hasattr(res, "words") and res.words:
                for w in res.words:
                    word_str = getattr(w, "word", "") or ""
                    start = float(getattr(w, "start", 0.0) or 0.0)
                    end = float(getattr(w, "end", 0.0) or 0.0)
                    words_list.append(
                        WordConfidence(
                            word=word_str.strip(),
                            start=round(start, 3),
                            end=round(end, 3),
                            probability=0.90,  # OpenAI API verbose_json doesn't export per-word logprobs
                            low_confidence=False,
                        )
                    )

            return STTResult(
                text=text.strip(),
                raw_text=text.strip(),
                words=words_list,
                language=language,
                duration=float(getattr(res, "duration", 0.0) or 0.0),
            )
        except Exception as exc:
            logger.error("OpenAIWhisperEngine failed: %s", exc)
            return STTResult(text="", raw_text="")


class DeepgramEngine(BaseSTTEngine):
    """Transcription via Deepgram Nova-2 / Nova-3 with keyword boosting."""

    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/webm",
        language: str = "en",
        prompt: Optional[str] = None,
        candidate_name: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        if not audio_bytes:
            return STTResult(text="", raw_text="")

        import app.services.speech as speech_mod

        text = speech_mod._transcribe_deepgram(
            audio_bytes=audio_bytes,
            content_type=content_type,
            language=language,
            candidate_name=candidate_name,
            prompt=prompt,
        )
        words_list = [
            WordConfidence(word=w, start=0.0, end=0.0, probability=0.90)
            for w in text.split()
        ]
        return STTResult(
            text=text,
            raw_text=text,
            words=words_list,
            language=language,
            duration=0.0,
        )


class AzureSpeechEngine(BaseSTTEngine):
    """Stub for Azure Cognitive Speech with phrase lists."""

    def __init__(self):
        self.subscription_key = os.environ.get("AZURE_SPEECH_KEY", "")
        self.region = os.environ.get("AZURE_SPEECH_REGION", "eastus")

    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/webm",
        language: str = "en",
        prompt: Optional[str] = None,
        candidate_name: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        if not self.subscription_key:
            logger.info("AzureSpeechEngine stub: AZURE_SPEECH_KEY not set. Returning empty result.")
            return STTResult(text="", raw_text="")

        logger.info("AzureSpeechEngine stub invoked with language=%s prompt=%s", language, prompt)
        return STTResult(text="", raw_text="")


_engine_cache: dict[str, BaseSTTEngine] = {}
_engine_cache_lock = Lock()


def get_stt_engine(engine_name: Optional[str] = None) -> BaseSTTEngine:
    """Factory to retrieve or create the configured STT engine singleton."""
    name = (engine_name or getattr(settings, "STT_ENGINE", None) or os.environ.get("STT_ENGINE", "whisper")).lower()

    with _engine_cache_lock:
        if name in _engine_cache:
            return _engine_cache[name]

        if name in ("whisper", "faster-whisper", "faster_whisper", "local"):
            engine = FasterWhisperEngine()
        elif name in ("openai", "openai-whisper"):
            engine = OpenAIWhisperEngine()
        elif name in ("deepgram", "nova-2", "nova-3"):
            engine = DeepgramEngine()
        elif name in ("azure", "azure-speech"):
            engine = AzureSpeechEngine()
        else:
            logger.warning("Unknown STT engine %r; defaulting to FasterWhisperEngine", name)
            engine = FasterWhisperEngine()

        _engine_cache[name] = engine
        return engine
