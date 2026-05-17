"""文档解析器单元测试"""

import io

from services.parser import parse_file, extract_text_from_txt


class TestTextExtraction:
    """文本提取测试"""

    def test_utf8_text(self):
        text = "Hello World 你好世界"
        result = extract_text_from_txt(text.encode("utf-8"))
        assert result == text

    def test_gbk_text(self):
        text = "中文测试"
        result = extract_text_from_txt(text.encode("gbk"))
        assert "中文测试" in result or "测试" in result

    def test_parse_txt(self):
        text = "简历内容"
        result = parse_file(text.encode("utf-8"), "resume.txt")
        assert result == "简历内容"

    def test_parse_python(self):
        code = "def hello():\n    return 'world'"
        result = parse_file(code.encode("utf-8"), "script.py")
        assert "def hello" in result
