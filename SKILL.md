---
name: tianyin-hifi-master
description: 从网易天音一键提取本人作品的无损 FLAC 母带，再加大音量并做分频段「音色 + 低频 + 高频」高清化母带处理，输出 FLAC / 24bit WAV / 44.1k16bit WAV。This skill should be used when the user asks to 提取/提出来/扒出 天音歌曲、拿母带或 FLAC、抱怨音量太小或音质糊/发闷/没有高频空气感与场域感、要求音质高清化、去 AI 化前准备干净母带，或要求对已有音频做低频厚度、中频音色、高频提亮、超高频整形、立体声拉宽与响度归一化。触发词：天音、母带、提出来、提取、加大音量、音质高清化、去糊、提亮、低频、高频、音色迁移、场域感、hifi 母带。
agent_created: true
---

# 天音母带提取与高清化链路

## Overview

把一首歌从「天音网页里的有损 mp3」变成「可交付的无损母带 + 商业响度 + 通透有场域感的高清版」，完整链路固化为一条命令。核心是三步：**① 网站提取真·无损 FLAC 母带 → ② 加大音量（响度归一化）→ ③ 分频段 + 音色高清化**。所有处理都保留原始母带不动，每一步都有独立成品，便于 A/B 对比。

**音质处理的硬性要求（不可省略）**：必须同时覆盖**音色**与**低频、高频**——低频厚度与低中频去糊、中频音色存在感、高频清晰度与空气感、超高频整形、立体声场宽度。这六段是默认值，不是可选项；调参只会改变幅度，不允许跳过整段处理。

## 何时使用

- 用户说「把《XXX》提出来 / 提取出来 / 拿母带」——指从天音账号下提取本人生成的作品。
- 用户说「音量太小 / 声音变小了」「听起来糊糊的 / 发闷 / 没有超高音质场域感」。
- 用户要「母带和 wav 都要」「转 24bit WAV」「给去 AI 化工具准备一份干净完整的 44.1k/16bit」。
- 用户拿一个本地音频来做响度/音色/频段优化（此时跳过提取，直接用 `master` 子命令）。

不适用：修复第三方工具造成的音频断裂 / 丢段——那是音频修复问题，不要用拼接或变速去补，应改用完整母带重新处理。

## 前置条件

- `ffmpeg` / `ffprobe` 在 PATH 中（需 4.4 以上，支持 loudnorm / alimiter）。
- 天音登录 Cookie（**每位使用者必须自备，仓库不含**）：优先级 `--cookie` > `TIANYIN_COOKIE` > `--cookie-file` / `TIANYIN_COOKIE_FILE` > 技能根目录 `cookie.txt` > `~/.workbuddy/tianyin_cookie.txt` > 当前目录 `cookie.txt`。获取与更新见 `references/tianyin_api.md`。
- `--tone-ref` 音色迁移额外需要 numpy（`pip install numpy`）；不带该参数时纯标准库 + ffmpeg 即可运行。
- 默认输出目录 `./out`（当前工作目录下）；可用 `--out`、环境变量 `TIANYIN_MASTER_OUT` 或技能根目录 `config.json` 的 `default_out` 覆盖。

## 主流程

### 一条龙（最常用）

```bash
python scripts/master_pipeline.py list "MySong"          # 先查 id，同名作品很多
python scripts/master_pipeline.py run "MySong" --id 123456789
```

`run` 依次执行：按歌名/id 定位作品 → 拼 `audioNosKey` 直链下载 FLAC（校验 `fLaC` 文件头）→ 生成「加音量」版 → 生成「高清化」版 → 转 24bit WAV 与 44.1k/16bit WAV → 写 `<歌名>_处理报告.json`。

**同名作品必须用 `--id` 精确指定**（资产里同名作品常有多个不同 id，取错会拿到别的歌）。`fetch` 遇到多匹配会直接报错并列出候选，不会自作主张选一个。

### 分步执行

```bash
python scripts/master_pipeline.py fetch "MySong" --id 123456789
python scripts/master_pipeline.py master "out/MySong.flac" --preset hifi
python scripts/master_pipeline.py measure "<任意音频>"        # 验证 LUFS / dBTP / LRA
```

### 输出文件

| 文件 | 内容 |
|---|---|
| `<歌名>.flac` | 原始无损母带，**永不覆盖** |
| `<歌名>_音量.flac` / `_音量.wav` | 仅响度归一化，不改音色（对比用） |
| `<歌名>_hifi.flac` / `_hifi.wav` | 完整分频段 + 音色 + 声场高清化（主交付） |
| `<歌名>_hifi_44k16.wav` | 44.1kHz/16bit，专供去 AI 化等外部工具重跑 |
| `<歌名>_处理报告.json` | 各成品的 LUFS / dBTP / LRA / 时长 / 体积 + 全部频段参数 |

## 分频段与音色处理（核心）

默认 `hifi` 预设的 ffmpeg 链，逐段含义：

| 频段 | 处理 | 默认 | 作用 |
|---|---|---|---|
| 次声 | `highpass=20` | — | 清掉无用的超低频，给响度留余量 |
| **低频 80Hz** | `equalizer` | **+1.0 dB** | 低频厚度/温暖感，避免提亮后变薄 |
| **低中频 320Hz** | `equalizer` | **−2.5 dB** | 去糊：清掉 AI 混音常见的箱感/泥泞 |
| **中频音色 2.5kHz** | `equalizer` | **+0.8 dB** | 音色存在感与质感，人声/乐器更靠前 |
| **高频 9kHz** | `treble` 高架 | **+3.5 dB** | 清晰度、细节、通透感 |
| **空气感 12kHz** | `equalizer` | **+2.0 dB** | 「超高音质」的空气感 |
| **超高频 18kHz** | `equalizer` | **−1.5 dB** | 整形：负值压 AI 高频毛刺更耐听，正值更亮更开阔 |
| 声场 | `extrastereo` | **1.20** | mid/side 加宽约 20%，做出场域感 |
| 响度 | `loudnorm` | **−11 LUFS / −1.0 dBTP / LRA 8** | 商业歌水平但保留瞬态，避免压成一团 |

全部参数都可用 CLI 覆盖：`--low --mud --mid --pres --air --tilt --width --target-lufs --loud-lufs --peak --lra`。

### 音色（三种粒度）

1. **参数化音色**：调 `--mid`（2.5kHz）、`--air`、`--tilt` 直接改 tonal balance。
2. **音色迁移 `--tone-ref <参考音频>`**：从参考音频学 1/3 倍频程长期平均频谱包络（**扣除整体电平差，只迁移相对音色形状**，音量交给响度归一化），用零相位 OLA 频域滤波套到目标上。用途：让完整母带听起来贴近另一份参考音频的暖厚质感。需 numpy，参考音频尽量用整首。
   ```bash
   python scripts/master_pipeline.py master "母带.flac" --tone-ref "去AI化版.wav" --preset hifi
   ```
3. **风格预设**：`hifi`（默认，通透均衡）/ `warm`（低频加厚、超高频收敛，暖厚人味）/ `air`（更亮更宽，场域感）/ `loud`（只加音量到 −10 LUFS）/ `flat`（仅响度，A/B 基准）。

常见听感对应调法：还嫌糊 → `--mud -3.5 --pres 4.5 --air 2.5`；嫌太亮刺耳 → `--tilt -3.0 --pres 2.0`；嫌薄 → `--low 2.5 --preset warm`；嫌不够响但别压糊 → 只调 `--loud-lufs`（响度版），别把 hifi 版目标推到 −9 以下。

## 验证（每次交付前必做）

```bash
python scripts/master_pipeline.py measure "<成品>"
ffmpeg -hide_banner -i "<成品>" -af silencedetect=noise=-40dB:d=0.15 -f null - 2>&1 | grep silence_start
ffprobe -hide_banner "<成品>" 2>&1 | grep -E "Duration|Audio"
```

检查：时长与原始母带一致（4:01.61 一类）、真实峰值 ≤ 0 dBTP、中段无新增静音、FLAC/WAV 规格正确。报告 JSON 里已有这些数值。

## 硬约束与已知坑

- **绝不要拿 `audioUrl` 的 mp3 当母带**：那是有损转码。母带只在 `audioNosKey`，拼出的直链前 4 字节必须是 `fLaC`，脚本已强制校验。
- **不要过度限幅**：把峰值已顶满的母带硬推到 −9/−8 LUFS 会压平瞬态、听感变糊（LRA 掉到 3 以下就是压过头）。`hifi` 版保持 −11 LUFS、LRA ≥ 3.5；要更响请用独立的「加音量」版，不要叠加。
- **不要覆盖原始母带**，也不要把同一首歌的多个 `.flac`/`.wav` 变体混放在同一目录里（部分工具会自动挑「最新一个」，容易选错）。交付后提示使用者按需只保留一份主文件。
- **升采样不会凭空长出 >24kHz 的超高频，EQ 加宽也不是真实房间混响**。当用户要「音乐厅般真实场域感」时如实说明那需要卷积混响（改混音，不是修母带）。
- **修补被删掉的音乐段落不在本 Skill 范围**：分段拼接/atempo 变速/循环延拓都会破坏节奏网格，实测会产生明显卡顿。正确解法是拿完整母带重新过一遍工具。
- Cookie 属于用户隐私，不要写进脚本、报告或日志。

## Resources

- `scripts/master_pipeline.py` — 全部功能单文件实现（list / fetch / master / run / measure），仅依赖标准库 + ffmpeg，音色迁移额外需 numpy。
- 仓库根目录 `README.md` / `install.py` — 面向使用者的安装说明与一键安装脚本。
- `references/tianyin_api.md` — 天音接口、字段含义、母带直链规律、Cookie 更新与排错。
- `references/mastering.md` — 响度标准、频段处理原理、参数安全区间、预设表、失败案例与取舍。
