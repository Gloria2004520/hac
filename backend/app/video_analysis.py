"""对本地已下载的视频做**真实**分析：读时长、找画面切点、抽代表帧。

这里只做「能拿证据的事」：
    ✓ 用 ffprobe 读真实的时长与分辨率
    ✓ 用 ffmpeg 的画面变化检测拿到真实的切点（不是猜的）
    ✓ 按时间点抽出真实的帧

刻意不做、也绝不假装做过的事：
    ✗ 没有语音转写（没接 ASR），所以不知道视频里到底讲了什么
    ✗ 没有 OCR、没有目标检测
    → 每个片段的**语义**只能靠视觉模型看代表帧来猜，必须如实标注。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

# 一趟解码里就采到的最低分（低于这个分数不记录），之后在 Python 里再按分数挑
SCENE_PROBE_THRESHOLD = 0.2
# 段数上限：代表帧要一次性发给模型，太多既贵又准不了
MAX_SEGMENTS = 10
# 两段之间至少隔多久，避免把连续闪回切成碎段
MIN_SEGMENT_SECONDS = 8.0
# 分数低于这个值认为不是真正的场景切换
MIN_SCENE_SCORE = 0.25
# 抽帧宽度：够模型看清，又不至于把请求撑大
FRAME_WIDTH = 640

_SCORE_RE = re.compile(r"lavfi\.scene_score=([0-9.]+)")
_TIME_RE = re.compile(r"pts_time:([0-9.]+)")


class AnalysisError(RuntimeError):
    """分析失败。消息直接给用户看，所以要说人话。"""


@dataclass
class VideoInfo:
    duration: float
    width: int | None
    height: int | None


def _which(name: str) -> str | None:
    """在 PATH 或 FFMPEG_LOCATION 指定的目录里找 ffmpeg/ffprobe。"""
    found = shutil.which(name)
    if found:
        return found

    configured = settings.ffmpeg_location
    if not configured:
        return None
    root = Path(configured)
    candidates = [root] if root.is_file() else [root, root / "bin"]
    for candidate in candidates:
        for suffix in (".exe", ""):
            binary = candidate / f"{name}{suffix}"
            if binary.is_file():
                return str(binary)
    return None


def ffmpeg_path() -> str:
    found = _which("ffmpeg")
    if not found:
        raise AnalysisError("服务端没找到 ffmpeg，装好后把 FFMPEG_LOCATION 指到它的目录。")
    return found


def ffprobe_path() -> str:
    found = _which("ffprobe")
    if not found:
        raise AnalysisError("服务端没找到 ffprobe（通常在 ffmpeg 同一个目录）。")
    return found


def _run(command: list[str], timeout: int, *, binary: bool = False):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError("分析视频超时了，视频可能太长或文件有问题。") from exc
    except OSError as exc:
        raise AnalysisError(f"调用 ffmpeg 失败：{exc}") from exc

    if result.returncode != 0:
        tail = (result.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1][:200] if tail else "没有更多信息"
        raise AnalysisError(f"ffmpeg 处理失败：{detail}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def probe_video(path: Path) -> VideoInfo:
    """读真实的时长与分辨率。"""
    if not path.is_file():
        raise AnalysisError("本地没有这个视频文件，可能还没下载完。")

    raw = _run(
        [
            ffprobe_path(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        timeout=60,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnalysisError("读不出视频信息，文件可能损坏。") from exc

    stream = (payload.get("streams") or [{}])[0]
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise AnalysisError("读不出视频时长，没法确定步骤边界。")

    return VideoInfo(duration=duration, width=stream.get("width"), height=stream.get("height"))


def parse_scene_output(text: str) -> list[tuple[float, float]]:
    """把 ffmpeg 的 metadata 输出解析成 [(时间秒, 画面变化分数)]。

    ffmpeg 先打印分数、再打印所属帧的头信息，所以按出现顺序两两配对。
    """
    scores = _SCORE_RE.findall(text)
    times = _TIME_RE.findall(text)
    if not scores or not times:
        return []
    if len(times) == len(scores) + 1:
        times = times[1:]  # 多出来的第一帧头信息不属于任何分数
    if len(scores) != len(times):
        raise AnalysisError("读不懂 ffmpeg 的场景检测输出，换个视频或重试一次。")

    pairs: list[tuple[float, float]] = []
    for score, time in zip(scores, times):
        try:
            pairs.append((float(time), float(score)))
        except ValueError:
            continue
    return pairs


def detect_scenes(path: Path, *, timeout: int = 600) -> list[tuple[float, float]]:
    """一趟拿到所有画面变化点及其分数（阈值放得很低，具体挑哪几个交给 Python）。

    默认只解码 I 帧（`-skip_frame nokey`）。实测这一步是整个流程里最费 CPU 的地方——
    146 秒的 1080p 全解码要 9.5 秒，只解 I 帧只要 1.4 秒（快 6.6 倍）。之所以成立，
    是因为真实切点几乎一定落在一个 I 帧上；代价是候选点会少一些、位置与全解码略有出入，
    但仍然是**真实的画面切换点**，不是猜的。
    想要和全解码完全一致的切点，把 .env 的 FAST_SCENE_DETECT 设成 false。

    注意：metadata 的输出必须走 stdout（`file=-`）。写临时文件是不行的——
    Windows 路径里的 `:` 会被 ffmpeg 的滤镜选项解析器当成分隔符，静默失败。
    """
    command = [ffmpeg_path(), "-hide_banner", "-nostdin"]
    if settings.fast_scene_detect:
        command += ["-skip_frame", "nokey"]
    command += [
        "-i", str(path),
        "-vf",
        f"select='gt(scene,{SCENE_PROBE_THRESHOLD})',"
        "metadata=mode=print:key=lavfi.scene_score:file=-",
        "-an",
        "-f", "null", "-",
    ]
    return parse_scene_output(_run(command, timeout=timeout))


def pick_cuts(
    scenes: list[tuple[float, float]],
    duration: float,
    *,
    max_cuts: int = MAX_SEGMENTS - 1,
    min_gap: float = MIN_SEGMENT_SECONDS,
    min_score: float = MIN_SCENE_SCORE,
) -> list[float]:
    """从画面变化点里挑出真正的步骤边界。

    按分数从高到低挑（画面变化越剧烈越像「换了一步」），并保证：
    - 两段之间至少隔 min_gap 秒（避免把连续快切切成一堆碎段）
    - 分数低于 min_score 的不算数
    - 最多 max_cuts 个切点（也就是最多 max_cuts+1 段）
    """
    ordered = sorted(scenes, key=lambda item: item[1], reverse=True)
    chosen: list[float] = []
    for time, score in ordered:
        if score < min_score:
            break
        if not 0 < time < duration:
            continue
        if any(abs(time - point) < min_gap for point in chosen):
            continue
        chosen.append(round(time, 1))
        if len(chosen) >= max_cuts:
            break
    return sorted(chosen)


def split_boundaries(cuts: list[float], duration: float) -> list[float]:
    """把切点变成「段」的边界：[0, c1, c2, ..., duration]。"""
    return [0.0, *cuts, round(duration, 1)]


def even_boundaries(duration: float, count: int) -> list[float]:
    """兜底：画面变化太少，切不出真实边界时，按总时长平均分。

    这条路**不是**画面切出来的，调用方必须把 basis 标成 even，别混进 shots。
    """
    count = max(1, min(count, MAX_SEGMENTS))
    step = duration / count
    return [round(index * step, 1) for index in range(count)] + [round(duration, 1)]


def frame_sample_time(start: float, end: float) -> float:
    """在一段里挑抽帧的时刻：取中间。

    不用段首——切点那一帧常常还是上一段的画面（或者刚好是转场黑帧），
    取中间更接近这一段「正常状态」的样子。
    """
    if end <= start:
        return max(0.0, start)
    return start + (end - start) / 2


def extract_frame(path: Path, at_seconds: float, *, width: int = FRAME_WIDTH) -> bytes:
    """抽某一时刻的画面，缩成小 JPEG 返回（给模型看、也给用户看）。"""
    return _run(
        [
            ffmpeg_path(),
            "-hide_banner", "-nostdin", "-loglevel", "error",
            "-ss", f"{max(0.0, at_seconds):.2f}",
            "-i", str(path),
            "-frames:v", "1",
            "-vf", f"scale={width}:-2",
            "-q:v", "5",
            "-f", "mjpeg",
            "-",
        ],
        timeout=60,
        binary=True,
    )


def _batched_extract_command(path: Path, times: list[float], width: int, out_dir: Path) -> list[str]:
    """一个 ffmpeg 进程、N 个输入，一次把 N 帧写进 out_dir。

    每个 `-ss` 都在对应的 `-i` **前面**（输入定位），所以只解要的那一帧，
    不会退化成「整段解码」。抽 6 帧从 2.5 秒降到 1.9 秒，段数越多省得越多。
    """
    command = [ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error"]
    for at in times:
        command += ["-ss", f"{at:.2f}", "-i", str(path)]
    for index in range(len(times)):
        command += [
            "-map", f"{index}:v:0",
            "-frames:v", "1",
            "-vf", f"scale={width}:-2",
            "-q:v", "5",
            str(out_dir / f"{index:03d}.jpg"),
        ]
    return command


def extract_frames(path: Path, at_seconds: list[float], *, width: int = FRAME_WIDTH) -> list[bytes]:
    """按时间点抽多帧。顺序与返回的列表一一对应，长度和入参一致。

    合并成一次调用只是为了省掉 N-1 次进程启动；任何一帧没抽出来就整体退回
    逐帧抽（`extract_frame`），所以结果和原实现完全等价——只是慢一点，不会更差。
    """
    times = [max(0.0, float(item)) for item in at_seconds]
    if not times:
        return []
    if len(times) == 1:
        return [extract_frame(path, times[0], width=width)]

    with tempfile.TemporaryDirectory(prefix="slowly-frames-") as temp_dir:
        out_dir = Path(temp_dir)
        try:
            _run(_batched_extract_command(path, times, width, out_dir), timeout=60 * len(times))
            frames = []
            for index in range(len(times)):
                frame_path = out_dir / f"{index:03d}.jpg"
                if not frame_path.is_file():
                    raise AnalysisError("合并抽帧少了帧，退回逐帧抽。")
                frames.append(frame_path.read_bytes())
            return frames
        except AnalysisError:
            return [extract_frame(path, at, width=width) for at in times]
