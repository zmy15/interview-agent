"""上传接口测试"""

import io


class TestUploadResume:
    """POST /upload/resume"""

    def test_upload_txt_resume(self, client):
        """上传 TXT 简历"""
        content = "张三\nPython 开发工程师\n3年经验"
        files = {"file": ("resume.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
        response = client.post("/upload/resume", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "resume.txt"
        assert "张三" in data["text"]
        assert data["type"] == "resume"

    def test_upload_invalid_extension(self, client):
        """上传不支持的文件类型"""
        content = b"test"
        files = {"file": ("image.png", io.BytesIO(content), "image/png")}
        response = client.post("/upload/resume", files=files)
        assert response.status_code == 400

    def test_upload_no_filename(self, client):
        """上传无文件名"""
        files = {"file": ("", io.BytesIO(b""), "application/octet-stream")}
        response = client.post("/upload/resume", files=files)
        assert response.status_code in (400, 422)


class TestUploadCode:
    """POST /upload/code"""

    def test_upload_python(self, client):
        """上传 Python 代码"""
        content = "def hello():\n    print('hello world')"
        files = {"file": ("test.py", io.BytesIO(content.encode("utf-8")), "text/x-python")}
        response = client.post("/upload/code", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.py"
        assert "hello" in data["text"]
        assert data["type"] == "code"
