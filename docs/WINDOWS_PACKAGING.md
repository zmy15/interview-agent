# Windows 客户端打包指南

把 Interview Agent 打包成「双击即用」的 Windows 客户端：无需安装
Python / Node，安装后双击桌面快捷方式即可运行。

## 快速开始

前提（只需安装一次）：

| 工具 | 版本要求 | 安装方式 |
|------|----------|----------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/)，安装时勾选 *Add python.exe to PATH* |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| Inno Setup 6 | 仅制作安装包需要 | `winget install JRSoft.InnoSetup` |

一条命令完成全部构建（前端 → PyInstaller → 安装包）：

```powershell
# 在项目根目录（ interview-agent/ ）执行
.\packaging\build_windows.ps1
```

产物：

| 文件 | 说明 |
|------|------|
| `dist\client\InterviewAgent\InterviewAgent.exe` | PyInstaller onedir，双击即用（免安装） |
| `dist\client\InterviewAgentSetup-<版本>.exe` | Inno Setup 安装包，分发给用户的就是这个 |

常用参数：

```powershell
.\packaging\build_windows.ps1 -SkipFrontend     # 前端已构建过，跳过（省 1 分钟）
.\packaging\build_windows.ps1 -SkipInstaller    # 只出 onedir，不装 Inno 也能构建
.\packaging\build_windows.ps1 -Version 1.1.0    # 指定安装包版本号
```

## 客户端的行为与源码运行的差异

| 项目 | 源码运行 | 打包客户端 |
|------|----------|------------|
| 启动方式 | `python desktop.py` 或 `start.bat` | 双击 `InterviewAgent.exe` |
| 依赖环境 | 需要 Python 3.11+ 与 pip 依赖 | 无需任何运行时 |
| 前端 | 需先 `npm run build` | 已内置构建产物 |
| 登录 | 默认单用户免登录（`.env` 可改） | 同为单用户免登录 |
| 数据位置 | 项目内 `data/`、`hf_cache/`、`logs/` | `%LOCALAPPDATA%\InterviewAgent\`（卸载不丢） |
| 配置位置 | 项目根 `.env` | 安装目录 `.env`（安装时已生成，可直接编辑） |
| 语音 STT/TTS | 可用（`.env` 开启） | **未包含**（默认关闭，开启时给出明确提示） |
| RAG 知识库 | 可用（装 `requirements-rag.txt`） | **未包含**（`RAG_ENABLED=false`） |

### 为什么语音和 RAG 没有打进包体

这两项依赖合计数百 MB（torch ~2GB、faster-whisper 模型 ~150MB、
piper 语音模型等），且**默认关闭**。为首发客户端做减法：

- 包体从 ~1.5GB 降到 ~300MB，下载和安装对小白友好；
- 代码里所有降级路径都已具备：`desktop.py` 的 `_MicroService.start`
  在冻结模式下直接跳过并说明原因；`main.py` 的语音路由注册有
  `try/except ImportError` 兜底；RAG 缺失时启动日志给出安装提示。

需要完整功能时，用源码方式运行即可（`start.bat` / `start.sh`），
行为与以前完全一致。

## 数据与配置位置

打包客户端遵循 Windows 应用数据规范（见 `app_paths.py`）：

```
%LOCALAPPDATA%\InterviewAgent\
├── data\          # SQLite 数据库（interview_platform.db）
├── hf_cache\      # HuggingFace 模型缓存（如启用 RAG 后的 embedding 模型）
├── logs\          # desktop.log 等服务日志
├── chroma_data\   # RAG 向量库（启用时）
└── screenshots\   # 截图答题的存档
```

配置文件 `.env` 在**安装目录**（与 `InterviewAgent.exe` 同级），
安装时由 `packaging/client.env` 生成，编辑后重启应用生效。

### 便携（绿色）模式

在安装目录下放一个空的 `portable_data\` 目录再启动，
所有可变数据改为写入安装目录下的 `portable_data\`，
可整个目录拷贝到 U 盘换电脑使用（数据不落用户目录）。

## 排障

| 症状 | 原因与处理 |
|------|------------|
| 启动后黑窗一闪而过 | 启动期日志写在控制台、随后自动隐藏。用 `--hide-console false` 运行可保留窗口排查 |
| 窗口打不开 / 白屏 | WebView2 运行时缺失（Win10/11 通常预装）。安装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) 后重试 |
| 「语音识别未连接」 | 打包版不含 STT。保持 `.env` 中 `VOICE_ENABLED=false` 即可，不影响其他功能 |
| 知识库上传不可用 | 打包版不含 RAG 依赖。用源码运行并安装 `requirements-rag.txt` |
| 数据库在哪 / 如何备份 | `%LOCALAPPDATA%\InterviewAgent\data\interview_platform.db`，直接拷贝该文件即可 |
| 端口被占用 | 启动器自动换用空闲端口；也可 `--port 8123` 指定 |

日志位置：`%LOCALAPPDATA%\InterviewAgent\logs\desktop.log`
（轮转 3 份、单份 2MB 上限）。

## 文件说明（`packaging/`）

| 文件 | 作用 |
|------|------|
| `client.env` | 打包内置的默认配置（安装时复制为安装目录的 `.env`） |
| `interview-agent.spec` | PyInstaller 打包配置（入口、数据、隐藏导入、排除项），顶部有完整设计说明 |
| `build_windows.ps1` | 一键构建脚本（环境检查 → 前端 → 打包 → 安装包） |
| `installer.iss` | Inno Setup 安装包脚本（免 UAC 用户级安装、桌面快捷方式） |

## 致维护者：新增模块后的检查清单

往项目里新增 `services/xxx.py` 或 `routers/xxx.py` 时，若它是
**函数内延迟 import**（PyInstaller 静态分析看不到），需要同步加进
`packaging/interview-agent.spec` 的 `HIDDEN_IMPORTS`，否则打包版
运行时才报 `ModuleNotFoundError`。

验证是否漏打包：源码运行正常的功能，在打包版里逐个点一遍。
