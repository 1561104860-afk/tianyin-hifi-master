#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
天音母带一站式链路：网站提取无损母带 -> 加大音量 -> 分频段/音色高清化。

依赖：Python 3.8+ 标准库 + ffmpeg（必需）；--tone-ref 音色迁移额外需要 numpy。
平台：Windows / macOS / Linux。所有路径、歌名支持中文。

子命令：
  list   [关键词]                       列出天音「我的资产」作品（含 id / 母带key）
  fetch  <歌名> [--id ID]              下载无损 FLAC 母带（校验 fLaC 文件头）
  master <音频文件>                     对本地音频做「加音量 + 全频段高清化」
  run    <歌名> [--id ID]              fetch + master 一条龙
  measure <音频文件>                    测量 LUFS / 真实峰值 / 动态范围

示例：
  python master_pipeline.py list MySong
  python master_pipeline.py run "MySong" --id 123456789
  python master_pipeline.py master "X.flac" --preset air --tone-ref "参考.wav"
"""
import argparse
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HOST = "https://music.163.com"
ASSET_API = "/api/rep/ai/factory/user/song/production/page"
REFERER = HOST + "/st/tianyin/my-assets"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """可选本地配置 config.json（已被 .gitignore 排除），可设 default_out。"""
    p = os.path.join(SKILL_DIR, "config.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def resolve_out(args):
    """输出目录优先级：--out > TIANYIN_MASTER_OUT > config.json > ./out"""
    if getattr(args, "out", None):
        return os.path.abspath(args.out)
    if os.environ.get("TIANYIN_MASTER_OUT"):
        return os.path.abspath(os.environ["TIANYIN_MASTER_OUT"])
    cfg = load_config().get("default_out")
    if cfg:
        return os.path.abspath(os.path.expanduser(cfg))
    return os.path.abspath(os.path.join(os.getcwd(), "out"))


COOKIE_CANDIDATES = [
    os.path.join(SKILL_DIR, "cookie.txt"),
    os.path.join(os.path.expanduser("~"), ".workbuddy", "tianyin_cookie.txt"),
    os.path.join(os.getcwd(), "cookie.txt"),
]

# 分频段默认参数（用户要求：必须包含音色、低频、高频处理）
PRESETS = {
    #              low   mud   mid  pres  air   tilt  width  lufs
    "hifi": dict(low=1.0,  mud=-2.5, mid=0.8,  pres=3.5, air=2.0,  tilt=-1.5, width=1.20, lufs=-11.0),
    "loud": dict(low=0.0,  mud=0.0,  mid=0.0,  pres=0.0, air=0.0,  tilt=0.0,  width=1.00, lufs=-10.0),
    "warm": dict(low=2.5,  mud=-2.0, mid=0.5,  pres=1.5, air=0.5,  tilt=-3.0, width=1.15, lufs=-9.5),
    "air":  dict(low=0.5,  mud=-3.0, mid=1.5,  pres=4.5, air=3.0,  tilt=1.0,  width=1.30, lufs=-11.0),
    "flat": dict(low=0.0,  mud=0.0,  mid=0.0,  pres=0.0, air=0.0,  tilt=0.0,  width=1.00, lufs=-11.0),
}

THIRD_OCTAVE = [25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500,
                630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300,
                8000, 10000, 12500, 16000, 20000]


# ---------------------------------------------------------------- 基础工具
def run(cmd, capture=False, quiet=True):
    if capture:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if quiet:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run(cmd)


def need_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("× 未找到 ffmpeg/ffprobe。请先安装（Windows: winget install Gyan.FFmpeg）。")


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]', "_", (s or "untitled").strip())[:80] or "untitled"


def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path], capture=True)
    try:
        return float(p.stdout.decode().strip())
    except Exception:
        return 0.0


def measure(path):
    """返回 LUFS / 真实峰值 / LRA / 时长 / 大小"""
    p = run(["ffmpeg", "-hide_banner", "-i", path,
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
             "-f", "null", "-"], capture=True)
    txt = p.stderr.decode("utf-8", "replace")
    def grab(k):
        m = re.search(r'"%s"\s*:\s*"(-?[\d.]+)"' % k, txt)
        return float(m.group(1)) if m else None
    return {
        "lufs": grab("input_i"), "tp": grab("input_tp"), "lra": grab("input_lra"),
        "duration_s": round(probe_duration(path), 2),
        "size_mb": round(os.path.getsize(path) / 1048576.0, 2),
    }


def fmt_m(d):
    return (f"{d['lufs']:.2f} LUFS / {d['tp']:+.2f} dBTP / LRA {d['lra']:.1f} / "
            f"{d['duration_s']:.2f}s / {d['size_mb']:.1f}MB") if d["lufs"] is not None else "测量失败"


# ---------------------------------------------------------------- 天音接口
def load_cookie(args):
    if getattr(args, "cookie", None):
        return args.cookie.strip()
    if os.environ.get("TIANYIN_COOKIE"):
        return os.environ["TIANYIN_COOKIE"].strip()
    cf = getattr(args, "cookie_file", None) or os.environ.get("TIANYIN_COOKIE_FILE")
    if cf:
        cf = os.path.expanduser(cf)
        if not os.path.exists(cf):
            sys.exit(f"× cookie 文件不存在: {cf}")
        return open(cf, encoding="utf-8").read().strip()
    for p in COOKIE_CANDIDATES:
        p = os.path.abspath(p)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read().strip()
            if txt:
                return txt
    sys.exit("× 找不到 cookie.txt。请把天音 Cookie 存到技能根目录的 cookie.txt，"
             "或用 --cookie-file / TIANYIN_COOKIE_FILE / TIANYIN_COOKIE 指定。"
             " 获取方式见 README.md 与 references/tianyin_api.md。")


def api_get(path, params, cookie):
    url = HOST + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Cookie": cookie, "Referer": REFERER,
        "Accept": "application/json, text/plain, */*",
    })
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_assets(cookie):
    items, offset = [], 0
    while True:
        r = api_get(ASSET_API, {"limit": 20, "offset": offset, "newVersion": "true"}, cookie)
        if r.get("code") not in (200, "200"):
            sys.exit(f"× 资产接口失败（Cookie 可能过期）: {json.dumps(r, ensure_ascii=False)[:300]}")
        lst = (r.get("data") or {}).get("songList") or []
        items += lst
        if len(lst) < 20:
            break
        offset += 20
    return items


def find_matches(items, keyword, pid=None):
    if pid:
        return [x for x in items if str(x.get("productionId")) == str(pid)]
    if not keyword:
        return items
    k = keyword.lower()
    return [x for x in items if k in str(x.get("name") or "").lower()]


def master_url(item):
    """从 audioNosKey 拼无损 FLAC 母带直链；缺失时用 id 模板兜底。"""
    key = item.get("audioNosKey") or ""
    if "/" in key:
        bucket, obj = key.split("/", 1)
        return f"http://{bucket}.nos.netease.com/{obj}"
    pid = item.get("productionId")
    if key:
        return f"http://music-ugc-ai-song.nos.netease.com/{key}"
    return f"http://music-ugc-ai-song.nos.netease.com/ai-factory-processed-{pid}-hq-online.flac"


def download_master(item, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    url = master_url(item)
    path = os.path.join(out_dir, safe_name(item.get("name")) + ".flac")
    print(f"  母带直链: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
        data = r.read()
    if data[:4] != b"fLaC" or len(data) < 1024 * 1024:
        sys.exit(f"× 下载内容不是有效 FLAC（头4字节={data[:4]!r}, {len(data)} 字节），请检查 audioNosKey / 登录态。")
    with open(path, "wb") as f:
        f.write(data)
    print(f"  √ 母带已保存: {path}  ({len(data)/1048576.0:.1f} MB, fLaC 校验通过)")
    return path


def cmd_list(args):
    items = fetch_assets(load_cookie(args))
    ms = find_matches(items, args.keyword, args.id)
    print(f"共 {len(items)} 个作品，匹配 {len(ms)} 个：\n")
    for i, x in enumerate(ms[:args.limit], 1):
        print(f"{i:>3}. {str(x.get('name'))[:34]:<34} id={x.get('productionId')}  "
              f"母带={'有' if x.get('audioNosKey') else '无'}")
    if len(ms) > args.limit:
        print(f"... 还有 {len(ms)-args.limit} 个")
    print("\n同名作品很多时务必用 --id 精确指定，避免拿错歌。")


def resolve_one(args):
    items = fetch_assets(load_cookie(args))
    ms = find_matches(items, args.keyword, args.id)
    if not ms:
        sys.exit("× 没有匹配的作品。先用 list 查一下歌名 / id。")
    if len(ms) > 1 and not args.id:
        print("× 匹配到多个作品，请用 --id 精确指定（避免拿错歌）：")
        for x in ms[:20]:
            print(f"    id={x.get('productionId')}  {x.get('name')}  "
                  f"submitTime={x.get('submitTime')}")
        sys.exit(1)
    return ms[0]


# ---------------------------------------------------------------- 音频处理链
def build_chain(o, stage):
    """stage=loud 仅响度；stage=hifi 完整分频段 + 音色 + 声场 + 响度。"""
    parts = []
    if stage == "hifi":
        # 低频：切除次声 + 80Hz 厚度（低频量感）
        parts.append("highpass=f=20")
        if o.low:
            parts.append(f"equalizer=f=80:width_type=o:width=1.0:g={o.low:.2f}")
        # 低中频去糊（AI 混音常见 300Hz 箱感/泥泞）
        if o.mud:
            parts.append(f"equalizer=f=320:width_type=o:width=0.8:g={o.mud:.2f}")
        # 中频音色：2.5kHz 存在感，决定「音色」的清晰度与质感
        if o.mid:
            parts.append(f"equalizer=f=2500:width_type=o:width=1.0:g={o.mid:.2f}")
        # 高频：9kHz 高架提清晰度 + 12kHz 空气感
        if o.pres:
            parts.append(f"treble=g={o.pres:.2f}:f=9000")
        if o.air:
            parts.append(f"equalizer=f=12000:width_type=o:width=1.5:g={o.air:.2f}")
        # 超高频整形：负值去 AI 生成毛刺/更耐听，正值更亮更有「场域感」
        if o.tilt:
            parts.append(f"equalizer=f=18000:width_type=o:width=1.0:g={o.tilt:.2f}")
        # 声场：mid/side 加宽
        if abs(o.width - 1.0) > 1e-6:
            parts.append(f"extrastereo=m={o.width:.3f}")
    lufs = o.loud_lufs if stage == "loud" else o.target_lufs
    parts.append(f"loudnorm=I={lufs:.1f}:TP={o.peak:.1f}:LRA={o.lra:.0f}:print_format=summary")
    return ",".join(parts)


def tone_transfer(src, ref, out_wav, sr=44100):
    """音色迁移：从参考音频学 1/3 倍频程长期频谱包络，零相位 OLA 滤波应用到 src。
    前置条件：numpy（pip install numpy）。"""
    try:
        import numpy as np
    except ImportError:
        sys.exit("× --tone-ref 需要 numpy。请执行 pip install numpy，"
                 "或用任一已装 numpy 的 Python 解释器运行本脚本。")

    def pcm(path):
        p = run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(sr),
                 "-f", "f32le", "-"], capture=True)
        return np.frombuffer(p.stdout, "<f4").reshape(-1, 2).copy()

    x, r = pcm(src), pcm(ref)
    if len(x) == 0 or len(r) == 0:
        sys.exit("× 音色迁移：音频解码失败")

    NFFT = 4096
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    win = np.hanning(NFFT)
    Pa, Pr = [], []
    for t in np.arange(1.0, min(len(x), len(r)) / sr - 0.2, 1.5):
        i = int(t * sr)
        fa, fr = x[i:i+NFFT, 0], r[i:i+NFFT, 0]
        if len(fa) < NFFT or len(fr) < NFFT:
            continue
        # 跳过静音/掉字窗口（去AI化成品常有静音洞），避免污染频谱统计
        if np.sqrt(np.mean(fa.astype(np.float64) ** 2)) < 1e-4:
            continue
        if np.sqrt(np.mean(fr.astype(np.float64) ** 2)) < 1e-4:
            continue
        Pa.append(np.abs(np.fft.rfft(fa * win)) ** 2)
        Pr.append(np.abs(np.fft.rfft(fr * win)) ** 2)
    if not Pa:
        sys.exit("× 音色迁移：音频太短，无法统计频谱")
    Pa, Pr = np.mean(Pa, 0), np.mean(Pr, 0)

    cg, raw_db = [], []
    for c in THIRD_OCTAVE:
        m = (freqs >= c / 2 ** (1/6)) & (freqs < c * 2 ** (1/6))
        if not m.any():
            continue
        db = 10 * np.log10((Pr[m].mean() + 1e-12) / (Pa[m].mean() + 1e-12))
        cg.append(c)
        raw_db.append(db)
    # 整体电平差不是「音色」：减中位数，只保留相对频谱形状（音量交给 loudnorm）
    level = float(np.median(raw_db))
    cd = [float(np.clip(d - level, -5, 5)) for d in raw_db]
    # 三点平滑：避免相邻 1/3 倍频程剧烈起伏造成梳状音色畸变
    cd = np.convolve(np.pad(cd, (1, 1), mode="edge"),
                     np.array([0.25, 0.5, 0.25]), mode="valid").tolist()
    lf = np.log2(np.maximum(freqs, 20))
    Hdb = np.interp(lf, np.log2(cg), cd)
    Hdb = np.convolve(np.pad(Hdb, (4, 4), mode="edge"), np.ones(9) / 9, mode="valid")
    H = 10 ** (Hdb / 20)
    H[0] = 1.0
    print(f"  已扣除整体电平差 {level:+.1f} dB（音量由响度归一化负责）")
    print("  音色迁移曲线(dB, 相对形状): " + " ".join(f"{c}:{d:+.1f}" for c, d in zip(cg, cd)))

    N, HOP = 4096, 2048
    w = np.hanning(N).astype("float32")
    norm = np.zeros(len(x), dtype=np.float32)
    y = np.zeros_like(x, dtype=np.float32)
    for s in range(0, len(x) - N, HOP):
        for ch in range(2):
            seg = x[s:s+N, ch] * w
            seg = np.fft.irfft(np.fft.rfft(seg) * H, n=N).astype("float32") * w
            y[s:s+N, ch] += seg
        norm[s:s+N] += w * w
    nz = norm > 1e-6
    for ch in range(2):
        y[nz, ch] /= norm[nz]
    y[~nz] = x[~nz]
    peak = float(np.max(np.abs(y)))
    if peak > 0.98:
        y *= 0.98 / peak

    p = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "2",
         "-i", "-", "-c:a", "pcm_f32le", out_wav],
        input=np.ascontiguousarray(y, dtype="<f4").tobytes(),
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.exit("× 音色迁移输出失败: " + p.stderr.decode("utf-8", "replace")[:300])
    return out_wav


def render(src, out_flac, chain):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
           "-af", chain, "-ar", "48000", "-c:a", "flac", "-sample_fmt", "s32", out_flac]
    p = run(cmd, capture=True)
    if p.returncode != 0:
        sys.exit("× ffmpeg 处理失败: " + p.stderr.decode("utf-8", "replace")[:500])


def cmd_master(args):
    need_ffmpeg()
    src = os.path.abspath(args.audio)
    if not os.path.exists(src):
        sys.exit(f"× 输入文件不存在: {src}")
    out_dir = resolve_out(args)
    os.makedirs(out_dir, exist_ok=True)
    name = args.name or os.path.splitext(os.path.basename(src))[0]
    name = re.sub(r"_hifi$|_音量$|_44k16$", "", name)

    work_src = src
    tmp_tone = os.path.join(out_dir, "_tone_tmp.wav")
    if args.tone_ref:
        print("① 音色迁移（1/3 倍频程频谱包络匹配）...")
        work_src = tone_transfer(src, os.path.abspath(args.tone_ref), tmp_tone)
        print(f"  √ 完成: {work_src}")

    print("② 加大音量（纯响度归一化，不改音色）...")
    loud_flac = os.path.join(out_dir, f"{name}_音量.flac")
    render(work_src, loud_flac, build_chain(args, "loud"))
    print("  √ " + fmt_m(measure(loud_flac)))

    print("③ 分频段 + 音色 + 声场高清化 ...")
    print("   低频 80Hz / 低中频 320Hz / 中频音色 2.5kHz / 高频 9k+12kHz / "
          "超高频 18kHz / 立体声宽度 / 响度")
    hifi_flac = os.path.join(out_dir, f"{name}_hifi.flac")
    render(work_src, hifi_flac, build_chain(args, "hifi"))
    print("  √ " + fmt_m(measure(hifi_flac)))

    made = {"原始母带": src, "加音量": loud_flac, "高清化": hifi_flac}
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    def wav_from(flac, suffix, rate, codec):
        w = os.path.join(out_dir, f"{name}{suffix}.wav")
        p = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", flac,
                 "-ar", str(rate), "-acodec", codec, w], capture=True)
        if p.returncode == 0:
            made[os.path.basename(w)] = w
            print(f"  √ {os.path.basename(w)}  {os.path.getsize(w)/1048576.0:.1f} MB")

    if "wav" in formats:
        wav_from(loud_flac, "_音量", 48000, "pcm_s24le")
        wav_from(hifi_flac, "_hifi", 48000, "pcm_s24le")
    if "pcm16" in formats:
        wav_from(hifi_flac, "_hifi_44k16", 44100, "pcm_s16le")
    if "flac" not in formats:
        # 用户明确不要 flac 时仍保留，因为它是无损基准；这里不删，只说明
        pass

    if os.path.exists(tmp_tone):
        os.remove(tmp_tone)

    report = {
        "name": name, "source": src, "preset": args.preset,
        "tone_ref": args.tone_ref,
        "bands": {"低频80Hz": args.low, "低中频320Hz": args.mud, "中频音色2.5kHz": args.mid,
                  "高频9kHz": args.pres, "空气感12kHz": args.air, "超高频18kHz": args.tilt,
                  "立体声宽度": args.width},
        "loudness": {"加音量目标": args.loud_lufs, "高清化目标": args.target_lufs,
                     "峰值上限dBTP": args.peak},
        "outputs": {k: (fmt_m(measure(v)) if v.lower().endswith((".wav", ".flac")) else v)
                    for k, v in made.items()},
    }
    rp = os.path.join(out_dir, f"{name}_处理报告.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n完成。报告: {rp}")
    print("输出目录: " + out_dir)
    return hifi_flac


# ---------------------------------------------------------------- 入口
def add_master_args(p):
    p.add_argument("--out", help="输出目录（默认 ./out；可用 TIANYIN_MASTER_OUT 或 config.json 改默认值）")
    p.add_argument("--name", help="输出文件名前缀（默认取输入文件名）")
    p.add_argument("--preset", default="hifi", choices=sorted(PRESETS),
                   help="预设：hifi(默认)/loud/warm/air/flat")
    p.add_argument("--tone-ref", help="音色迁移参考音频（把它的频谱包络套到目标上，需 numpy）")
    p.add_argument("--low", type=float, help="低频 80Hz 厚度 dB（默认 +1.0）")
    p.add_argument("--mud", type=float, help="低中频 320Hz 去糊 dB（默认 -2.5）")
    p.add_argument("--mid", type=float, help="中频音色 2.5kHz 存在感 dB（默认 +0.8）")
    p.add_argument("--pres", type=float, help="高频 9kHz 清晰度 dB（默认 +3.5）")
    p.add_argument("--air", type=float, help="12kHz 空气感 dB（默认 +2.0）")
    p.add_argument("--tilt", type=float, help="18kHz 超高频整形 dB（默认 -1.5，正值更亮）")
    p.add_argument("--width", type=float, help="立体声宽度（默认 1.20，1.0=不加宽）")
    p.add_argument("--target-lufs", type=float, help="高清化版响度目标（默认 -11）")
    p.add_argument("--loud-lufs", type=float, default=-10.0, help="纯加音量版目标（默认 -10）")
    p.add_argument("--peak", type=float, default=-1.0, help="真实峰值上限 dBTP（默认 -1.0）")
    p.add_argument("--lra", type=float, default=8, help="loudnorm 目标 LRA（默认 8）")
    p.add_argument("--formats", default="flac,wav,pcm16",
                   help="输出容器，逗号分隔：flac,wav,pcm16（44.1k/16bit 供去AI化工具）")


def apply_preset(args):
    d = dict(PRESETS[args.preset])
    user = {k: getattr(args, k, None) for k in ("low", "mud", "mid", "pres", "air", "tilt", "width")}
    for k, v in user.items():
        if v is not None:
            d[k] = v
    for k in ("low", "mud", "mid", "pres", "air", "tilt", "width"):
        setattr(args, k, d[k])
    if getattr(args, "target_lufs", None) is None:
        args.target_lufs = d["lufs"]
    return args


def main():
    ap = argparse.ArgumentParser(description="天音母带：提取 -> 加音量 -> 分频段/音色高清化")
    ap.add_argument("--cookie", help="直接传入 Cookie 字符串")
    ap.add_argument("--cookie-file", help="cookie.txt 路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出天音作品")
    p.add_argument("keyword", nargs="?", default="", help="歌名关键词")
    p.add_argument("--id", help="按 id 过滤")
    p.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("fetch", help="下载无损 FLAC 母带")
    p.add_argument("keyword", help="歌名")
    p.add_argument("--id", help="作品 id（同名时必须指定）")
    p.add_argument("--out", help="输出目录（默认 ./out）")

    p = sub.add_parser("master", help="处理本地音频")
    p.add_argument("audio", help="输入音频（flac/wav/mp3 均可）")
    add_master_args(p)

    p = sub.add_parser("run", help="fetch + master 一条龙")
    p.add_argument("keyword", help="歌名")
    p.add_argument("--id", help="作品 id（同名时必须指定）")
    add_master_args(p)

    p = sub.add_parser("measure", help="测量响度/峰值/动态")
    p.add_argument("audio")

    args = ap.parse_args()
    need_ffmpeg()

    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "measure":
        print(fmt_m(measure(os.path.abspath(args.audio))))
    elif args.cmd == "fetch":
        item = resolve_one(args)
        print(f"提取: {item.get('name')}  id={item.get('productionId')}")
        download_master(item, resolve_out(args))
    elif args.cmd == "master":
        apply_preset(args)
        cmd_master(args)
    elif args.cmd == "run":
        apply_preset(args)
        item = resolve_one(args)
        print(f"提取: {item.get('name')}  id={item.get('productionId')}")
        src = download_master(item, resolve_out(args))
        if not args.name:
            args.name = safe_name(item.get("name"))
        args.audio = src
        cmd_master(args)


if __name__ == "__main__":
    main()
