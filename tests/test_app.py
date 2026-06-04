import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app import DEFAULT_REQUEST, print_llm_summary, read_user_prompt


class FakeMessage:
    content = "这是模型补充分析。"


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]


class FakeCompletions:
    def create(self, **_: object) -> FakeResponse:
        return FakeResponse()


class FakeChat:
    completions = FakeCompletions()


class FakeClient:
    chat = FakeChat()


class LLMSummaryTest(unittest.TestCase):
    def test_print_llm_summary_outputs_model_summary(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            print_llm_summary(
                llm_config=(FakeClient(), "fake-model"),  # type: ignore[arg-type]
                llm_summary_enabled=True,
                user_prompt="分析简历",
                resume_text="Python FastAPI",
                jd_text="需要 Python",
                match_result='{"match_score": 80}',
            )

        self.assertIn("模型补充分析", output.getvalue())
        self.assertIn("这是模型补充分析。", output.getvalue())


class PromptInputTest(unittest.TestCase):
    def test_read_user_prompt_uses_default_in_demo_mode(self) -> None:
        self.assertEqual(read_user_prompt(demo=True), DEFAULT_REQUEST)

    def test_read_user_prompt_joins_request_parts(self) -> None:
        self.assertEqual(read_user_prompt(["分析", "候选人"]), "分析 候选人")

    def test_read_user_prompt_uses_default_when_stdin_is_not_interactive(self) -> None:
        with patch("sys.stdin.isatty", return_value=False):
            self.assertEqual(read_user_prompt(), DEFAULT_REQUEST)


if __name__ == "__main__":
    unittest.main()
