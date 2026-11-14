import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.speech import correct_profile_terms, transcribe_audio


class SpeechServiceTests(unittest.TestCase):
    def setUp(self):
        self._orig_engine = getattr(settings, "STT_ENGINE", "whisper")
        settings.STT_ENGINE = "deepgram"

    def tearDown(self):
        settings.STT_ENGINE = self._orig_engine

    def test_empty_audio_returns_empty_string(self):
        result = transcribe_audio(b"")
        self.assertEqual(result, "")

    def test_missing_api_key_returns_empty_string(self):
        with patch.object(settings, "DEEPGRAM_API_KEY", ""):
            result = transcribe_audio(b"some_audio_bytes")
            self.assertEqual(result, "")

    @patch("app.services.speech._get_deepgram_client")
    def test_deepgram_sdk_transcription_raw_result(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock Deepgram SDK response structure
        mock_alt = MagicMock()
        mock_alt.transcript = "Hello, my name is Abhinav and I am excited for this backend role."
        mock_channel = MagicMock()
        mock_channel.alternatives = [mock_alt]
        mock_response = MagicMock()
        mock_response.results.channels = [mock_channel]
        mock_client.listen.v1.media.transcribe_file.return_value = mock_response

        with patch.object(settings, "DEEPGRAM_API_KEY", "mock_key_123"):
            transcript = transcribe_audio(
                b"valid_audio_bytes",
                content_type="audio/webm",
                language="en",
                candidate_name="Arjun Mehta",
                resume_summary="Senior Engineer at IIT Delhi",
            )

        # Ensure verbatim raw transcript is returned without name guessing or alteration
        self.assertEqual(
            transcript,
            "Hello, my name is Abhinav and I am excited for this backend role.",
        )

        # Verify correct Deepgram parameters including candidate name keyword boosting
        mock_client.listen.v1.media.transcribe_file.assert_called_once_with(
            request=b"valid_audio_bytes",
            model="nova-2",
            smart_format=True,
            punctuate=True,
            language="en",
            keywords=["Arjun:5", "Mehta:5"],
        )

    @patch("httpx.Client")
    @patch("app.services.speech._get_deepgram_client")
    def test_deepgram_http_fallback_path(self, mock_get_client, mock_httpx_cls):
        # Force SDK to fail so fallback HTTP triggers
        mock_get_client.return_value = None

        mock_http_instance = MagicMock()
        mock_httpx_cls.return_value.__enter__.return_value = mock_http_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "I designed scalable microservices using PostgreSQL and Python."
                            }
                        ]
                    }
                ]
            }
        }
        mock_http_instance.post.return_value = mock_response

        with patch.object(settings, "DEEPGRAM_API_KEY", "mock_key_123"):
            transcript = transcribe_audio(b"audio_payload", content_type="audio/webm")

        self.assertEqual(
            transcript,
            "I designed scalable microservices using PostgreSQL and Python.",
        )

    def test_correct_profile_terms_is_passthrough(self):
        sample = "Hi, I am Abhinav and I worked on Redis caching."
        self.assertEqual(correct_profile_terms(sample, "DifferentName"), sample)

    def test_websocket_transcribe_warning_without_api_key(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with patch.object(settings, "DEEPGRAM_API_KEY", ""):
            client = TestClient(app)
            with client.websocket_connect("/api/v1/interview/ws/transcribe") as websocket:
                data = websocket.receive_json()
                self.assertEqual(data.get("type"), "warning")
                self.assertIn("DEEPGRAM_API_KEY not configured", data.get("message", ""))


if __name__ == "__main__":
    unittest.main()
