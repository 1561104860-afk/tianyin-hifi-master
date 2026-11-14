# tianyin-hifi-master

从网易天音提取**本人作品的无损 FLAC 母带**，一键完成「加大音量 + 音色 / 低频 / 高频高清化」，输出 FLAC、24bit WAV 与 44.1k/16bit WAV。

既是一个 [WorkBuddy](https://www.workbuddy.cn/) Skill，也可以当独立命令行工具使用。**零 Python 第三方依赖**（仅标准库 + ffmpeg）；只有可选的音色迁移需要 numpy。

---

## 它能解决什么

天音主站「我的资产」只暴露 `audioUrl`（有损 mp3）。但作品对象里的 `audioNosKey` 指向真正的无损 FLAC 母带（48kHz / 24bit）。本工具把这条链路固化下来：

1. **提取**：按歌名 + id 定位作品 → 拼出母带直链 → 下载并校验 `fLaC` 文件头。
2. **加大音量**：EBU R128 响度归一化到商业歌曲水平，带真实峰值保护，不削波。
3. **高清化**：分频段 + 音色 + 声场处理 → 输出多格式成品与处理报告。

### 六段频段处理（默认全部启用）

| 频段 | 默认值 | 作用 |
|---|---|---|
| 低频 80Hz | +1.0 dB | 低频厚度、温暖感 |
| 低中频 320Hz | −2.5 dB | 去糊、清掉 AI 混音的箱感泥泞 |
| 中频音色 2.5kHz | +0.8 dB | 音色存在感与质感 |
| 高频 9kHz | +3.5 dB | 清晰度、细节 |
| 空气感 12kHz | +2.0 dB | 通透、超高频听感 |
| 超高频 18kHz | −1.5 dB | 整形（正值更亮，负值去毛刺更耐听） |
| 声场 | ×1.20 | mid/side 加宽，做出场域感 |
| 响度 | −11 LUFS / −1.0 dBTP | 商业歌水平，但保留瞬态 |

「音色」还有两种粒度：参数化 EQ（每段都可调）、`--tone-ref` 音色迁移（从参考音频学 1/3 倍频程频谱包络）。详见 [references/mastering.md](references/mastering.md)。

---

## 快速开始（3 步）

### 1. 安装 ffmpeg

```bash
# Windows
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt install ffmpeg
```

验证：`ffmpeg -version`。

### 2. 放 Cookie（**每位使用者必须自备**）

1. Chrome / Edge 打开 `https://music.163.com/st/tianyin/my-assets` 并登录；
2. F12 → Network → 任意发往 `music.163.com` 的请求 → Request Headers → 复制**整行 Cookie**；
3. 在项目根目录新建 `cookie.txt`，粘贴为**一行**（不要换行）。

也可以把 Cookie 放到 `~/.workbuddy/tianyin_cookie.txt`，或用环境变量 `TIANYIN_COOKIE` / `TIANYIN_COOKIE_FILE` 传入。

> `cookie.txt` 已被 `.gitignore` 排除，**绝不会、也绝不应该被提交**。仓库里只有不含真实凭证的 `cookie.example.txt` 模板。

### 3. 跑起来

```bash
python scripts/master_pipeline.py list "歌名关键词"        # 先查 id（同名作品很多）
python scripts/master_pipeline.py run "歌名" --id 12345678  # 一条龙：提取 → 加音量 → 高清化
```

成品默认输出到 `./out/`，并生成 `<歌名>_处理报告.json`（含 LUFS / dBTP / LRA / 时长 / 全部频段参数）。

---

## 安装方式

### A. WorkBuddy 用户（推荐）

从 **Releases** 下载 `tianyin-hifi-master.zip`，解压到用户级技能目录：

```
~/.workbuddy/skills/tianyin-hifi-master/
```

或者 clone 本仓库后运行一键安装：

```bash
python install.py                 # 安装到 ~/.workbuddy/skills/tianyin-hifi-master
python install.py --target "~/my-skills/tianyin-hifi-master"   # 自定义位置
```

然后把 `cookie.txt` 放到安装后的技能目录内。之后直接对 WorkBuddy 说「把《XXX》提出来」「这首歌音质高清化一下」即可自动触发。

### B. 独立命令行

```bash
git clone https://github.com/1561104860-afk/tianyin-hifi-master.git
cd tianyin-hifi-master
# 放 cookie.txt
python scripts/master_pipeline.py run "MySong" --id 123456789
```

---

## 命令

| 命令 | 作用 |
|---|---|
| `list [关键词] [--id ID]` | 列出天音作品（id / 是否有母带） |
| `fetch <歌名> --id ID` | 只下载无损 FLAC 母带 |
| `master <音频文件>` | 对本地音频做「加音量 + 全频段高清化」 |
| `run <歌名> --id ID` | fetch + master 一条龙 |
| `measure <音频文件>` | 测量 LUFS / dBTP / LRA |

常用参数：

```bash
--preset hifi|warm|air|loud|flat   # 风格预设，默认 hifi
--low --mud --mid --pres --air --tilt --width   # 逐段覆盖频段增益
--target-lufs -11 --peak -1.0      # 响度与峰值上限
--tone-ref "参考.wav"              # 音色迁移（需 numpy）
--formats flac,wav,pcm16           # 输出格式
--out DIR                          # 输出目录
```

预设：`hifi` 通透均衡（默认）/ `warm` 暖厚人味 / `air` 更亮更宽 / `loud` 只加音量 / `flat` A-B 基准。

### 输出文件

| 文件 | 内容 |
|---|---|
| `<歌名>.flac` | 原始无损母带（永不覆盖） |
| `<歌名>_音量.flac/.wav` | 仅响度归一化，不改音色 |
| `<歌名>_hifi.flac/.wav` | 完整高清化（主交付） |
| `<歌名>_hifi_44k16.wav` | 44.1kHz/16bit，供去 AI 化等外部工具重跑 |
| `<歌名>_处理报告.json` | 各成品客观指标 + 全部处理参数 |

---

## 配置优先级

| 项目 | 优先级（从高到低） |
|---|---|
| Cookie | `--cookie` → `TIANYIN_COOKIE` → `--cookie-file` / `TIANYIN_COOKIE_FILE` → 技能根目录 `cookie.txt` → `~/.workbuddy/tianyin_cookie.txt` → 当前目录 `cookie.txt` |
| 输出目录 | `--out` → `TIANYIN_MASTER_OUT` → `config.json` 的 `default_out` → `./out` |

想固定默认输出目录：把 `config.example.json` 复制为 `config.json` 并改 `default_out`（`config.json` 已被 `.gitignore` 排除）。

---

## 常见问题

**`资产接口失败` / code 非 200**：Cookie 过期，重新复制一次即可。编辑器接口失败不影响本工具。

**同名作品拿错了**：资产里同名很常见，务必先 `list` 查 id 再传 `--id`；`fetch`/`run` 遇到多匹配会主动报错，不会擅自选一个。

**`--tone-ref` 报缺 numpy**：`pip install numpy`，或用任一已装 numpy 的 Python 运行脚本。

**为什么不用官方 mp3**：那是 320kbps 有损转码；mp3→wav 只是换容器，音质上限不变。母带只在 `audioNosKey`。

**能变出真·Hi-Res 超高频吗**：不能。源是 48kHz/24bit，最高到 24kHz；升采样不会凭空产生新频率，EQ 加宽也不是真实房间混响。本工具做的是听感优化，不伪造信息。

**修「去 AI 化工具挖出的停顿」**：不要拼接或变速补洞，会破坏节奏网格产生卡顿。正确做法是用干净完整母带重新过一遍工具。

更多原理与排错见 [references/tianyin_api.md](references/tianyin_api.md) 与 [references/mastering.md](references/mastering.md)。

---

## 合规与免责

- 本工具**仅用于下载你本人账号下、由你本人创作或拥有的作品**，请遵守网易天音服务协议与相关法律法规；请勿用于获取、分发他人作品或绕过平台授权。
- 工具不提供任何 Cookie、不绕过登录、不破解加密，只调用网页自身使用的明文接口读取本人资产列表。
- Cookie 等同账号凭证：**不要提交、不要分享、不要写进 Issue 或日志**。
- 音频处理属听感优化，效果因曲目而异；请保留原始母带以便回退。
- 作者与贡献者对使用者的使用方式及由此产生的后果不承担责任。

## License

[MIT](LICENSE)
