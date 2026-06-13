from __future__ import annotations

import asyncio
import gzip
import json
import struct
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.shared import get_logger
from backend.shared.config import (
    VOLCENGINE_ASR_ACCESS_KEY,
    VOLCENGINE_ASR_API_KEY,
    VOLCENGINE_ASR_APP_KEY,
    VOLCENGINE_ASR_ENABLE_DDC,
    VOLCENGINE_ASR_ENABLE_ITN,
    VOLCENGINE_ASR_ENABLE_PUNC,
    VOLCENGINE_ASR_LANGUAGE,
    VOLCENGINE_ASR_MODEL,
    VOLCENGINE_ASR_RESOURCE_ID,
    VOLCENGINE_ASR_SEGMENT_DURATION,
    VOLCENGINE_ASR_SHOW_UTTERANCES,
    VOLCENGINE_ASR_TIMEOUT,
    VOLCENGINE_ASR_WS_URL,
)


logger = get_logger("llm.volc_asr")

DEFAULT_SAMPLE_RATE = 16000


class ProtocolVersion:
    V1 = 0b0001


class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111


class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011


class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001


class CompressionType:
    NO_COMPRESSION = 0b0000
    GZIP = 0b0001


@dataclass(frozen=True)
class VolcASRConfig:
    asr_model: str = "bigmodel"
    language: str = "zh-CN"
    ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
    resource_id: str = "volc.bigasr.sauc.duration"
    api_key: str = ""
    app_key: str = ""
    access_key: str = ""
    segment_duration_ms: int = 200
    timeout_seconds: float = 60.0
    enable_itn: bool = True
    enable_punc: bool = True
    enable_ddc: bool = True
    show_utterances: bool = True


def load_volc_asr_config() -> VolcASRConfig:
    return VolcASRConfig(
        asr_model=VOLCENGINE_ASR_MODEL,
        language=VOLCENGINE_ASR_LANGUAGE,
        ws_url=VOLCENGINE_ASR_WS_URL,
        resource_id=VOLCENGINE_ASR_RESOURCE_ID,
        api_key=VOLCENGINE_ASR_API_KEY,
        app_key=VOLCENGINE_ASR_APP_KEY,
        access_key=VOLCENGINE_ASR_ACCESS_KEY,
        segment_duration_ms=VOLCENGINE_ASR_SEGMENT_DURATION,
        timeout_seconds=VOLCENGINE_ASR_TIMEOUT,
        enable_itn=VOLCENGINE_ASR_ENABLE_ITN,
        enable_punc=VOLCENGINE_ASR_ENABLE_PUNC,
        enable_ddc=VOLCENGINE_ASR_ENABLE_DDC,
        show_utterances=VOLCENGINE_ASR_SHOW_UTTERANCES,
    )


async def transcribe_audio_bytes(
    *,
    audio_bytes: bytes,
    mime_type: str,
    filename: str,
    config: VolcASRConfig,
    language: str | None = None,
) -> dict[str, Any]:
    try:
        import aiohttp
    except Exception as exc:
        raise RuntimeError("缺少 aiohttp 依赖，无法调用火山 ASR WebSocket") from exc

    if not audio_bytes:
        raise ValueError("audio_bytes 不能为空")
    if not config.resource_id:
        raise ValueError("VOLCENGINE_ASR_RESOURCE_ID 未配置")
    if not config.ws_url:
        raise ValueError("VOLCENGINE_ASR_WS_URL 未配置")
    if not config.api_key and not (config.app_key and config.access_key):
        raise ValueError("火山 ASR 鉴权未配置")

    pcm_bytes = _convert_audio_to_standard_pcm(audio_bytes, mime_type=mime_type, filename=filename)
    sample_width = 2
    channel_num = 1
    frame_rate = DEFAULT_SAMPLE_RATE
    segment_size = max(1, channel_num * sample_width * frame_rate * config.segment_duration_ms // 1000)
    connect_id = str(uuid.uuid4())

    headers = _build_auth_headers(config=config, connect_id=connect_id)
    timeout = aiohttp.ClientTimeout(total=config.timeout_seconds)
    latest_payload: dict[str, Any] = {}
    latest_text = ""
    sequence = 1

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(config.ws_url, headers=headers) as conn:
            await conn.send_bytes(
                _new_full_client_request(
                    seq=sequence,
                    config=config,
                    language=(language or config.language or "").strip() or "zh-CN",
                )
            )
            sequence += 1

            full_response = await conn.receive()
            if full_response.type != aiohttp.WSMsgType.BINARY:
                raise RuntimeError("火山 ASR 握手后未返回二进制响应")
            parsed = _parse_response(full_response.data)
            latest_payload = parsed.get("payload_msg") or {}
            latest_text = _extract_text_from_payload(latest_payload) or latest_text

            chunks = [pcm_bytes[i : i + segment_size] for i in range(0, len(pcm_bytes), segment_size)]
            for index, chunk in enumerate(chunks):
                is_last = index == len(chunks) - 1
                await conn.send_bytes(_new_audio_only_request(seq=sequence, segment=chunk, is_last=is_last))
                msg = await conn.receive()
                if msg.type != aiohttp.WSMsgType.BINARY:
                    raise RuntimeError("火山 ASR 未返回二进制响应")
                parsed = _parse_response(msg.data)
                payload_msg = parsed.get("payload_msg") or {}
                text = _extract_text_from_payload(payload_msg)
                if payload_msg:
                    latest_payload = payload_msg
                if text:
                    latest_text = text
                if parsed.get("code", 0) not in {0, 20000000}:
                    raise ValueError(f"火山 ASR 返回错误码: {parsed.get('code')}")
                if parsed.get("is_last_package"):
                    break
                if not is_last:
                    sequence += 1
                await asyncio.sleep(config.segment_duration_ms / 1000)

    if not latest_text:
        raise ValueError("火山 ASR 未返回识别文本")
    return {
        "text": latest_text,
        "raw": latest_payload,
        "model": config.asr_model,
    }


def _build_auth_headers(*, config: VolcASRConfig, connect_id: str) -> dict[str, str]:
    headers = {
        "X-Api-Resource-Id": config.resource_id,
        "X-Api-Request-Id": connect_id,
        "X-Api-Connect-Id": connect_id,
        "X-Api-Sequence": "-1",
    }
    if config.api_key:
        headers["X-Api-Key"] = config.api_key
    else:
        headers["X-Api-App-Key"] = config.app_key
        headers["X-Api-Access-Key"] = config.access_key
    return headers


def _new_full_client_request(*, seq: int, config: VolcASRConfig, language: str) -> bytes:
    payload = {
        "user": {
            "uid": "robotclaw",
        },
        "audio": {
            "format": "pcm",
            "codec": "raw",
            "rate": DEFAULT_SAMPLE_RATE,
            "bits": 16,
            "channel": 1,
            "language": language,
        },
        "request": {
            "model_name": config.asr_model,
            "enable_itn": config.enable_itn,
            "enable_punc": config.enable_punc,
            "enable_ddc": config.enable_ddc,
            "show_utterances": config.show_utterances,
            "enable_nonstream": False,
        },
    }
    return _build_request_frame(
        message_type=MessageType.CLIENT_FULL_REQUEST,
        flags=MessageTypeSpecificFlags.POS_SEQUENCE,
        serialization_type=SerializationType.JSON,
        payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        sequence=seq,
        compress=True,
    )


def _new_audio_only_request(*, seq: int, segment: bytes, is_last: bool) -> bytes:
    return _build_request_frame(
        message_type=MessageType.CLIENT_AUDIO_ONLY_REQUEST,
        flags=MessageTypeSpecificFlags.NEG_WITH_SEQUENCE if is_last else MessageTypeSpecificFlags.POS_SEQUENCE,
        serialization_type=SerializationType.NO_SERIALIZATION,
        payload=segment,
        sequence=-seq if is_last else seq,
        compress=True,
    )


def _build_request_frame(
    *,
    message_type: int,
    flags: int,
    serialization_type: int,
    payload: bytes,
    sequence: int,
    compress: bool,
) -> bytes:
    compressed_payload = gzip.compress(payload) if compress else payload
    header = bytearray()
    header.append((ProtocolVersion.V1 << 4) | 1)
    header.append((message_type << 4) | flags)
    header.append((serialization_type << 4) | (CompressionType.GZIP if compress else CompressionType.NO_COMPRESSION))
    header.append(0x00)

    frame = bytearray(header)
    frame.extend(struct.pack(">i", sequence))
    frame.extend(struct.pack(">I", len(compressed_payload)))
    frame.extend(compressed_payload)
    return bytes(frame)


def _parse_response(message: bytes) -> dict[str, Any]:
    header_size = message[0] & 0x0F
    message_type = message[1] >> 4
    flags = message[1] & 0x0F
    serialization_type = message[2] >> 4
    compression_type = message[2] & 0x0F
    payload = message[header_size * 4 :]

    response: dict[str, Any] = {
        "code": 0,
        "is_last_package": bool(flags & 0x02),
        "payload_sequence": 0,
        "payload_size": 0,
        "payload_msg": None,
    }
    if flags & 0x01:
        response["payload_sequence"] = struct.unpack(">i", payload[:4])[0]
        payload = payload[4:]

    if message_type == MessageType.SERVER_FULL_RESPONSE:
        response["payload_size"] = struct.unpack(">I", payload[:4])[0]
        payload = payload[4:]
    elif message_type == MessageType.SERVER_ERROR_RESPONSE:
        response["code"] = struct.unpack(">i", payload[:4])[0]
        response["payload_size"] = struct.unpack(">I", payload[4:8])[0]
        payload = payload[8:]

    if compression_type == CompressionType.GZIP and payload:
        payload = gzip.decompress(payload)

    if serialization_type == SerializationType.JSON and payload:
        response["payload_msg"] = json.loads(payload.decode("utf-8"))
        if isinstance(response["payload_msg"], dict):
            response["code"] = int(response["payload_msg"].get("code", response["code"]) or response["code"])
    return response


def _extract_text_from_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result")
    if isinstance(result, dict):
        return str(result.get("text", "")).strip()
    if isinstance(result, list):
        texts = []
        for item in result:
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if text:
                    texts.append(text)
        return " ".join(texts).strip()
    return str(payload.get("text", "")).strip()


def _convert_audio_to_standard_pcm(audio_bytes: bytes, *, mime_type: str, filename: str) -> bytes:
    suffix = Path(filename or _filename_for_mime(mime_type)).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as source:
        source.write(audio_bytes)
        source_path = Path(source.name)
    try:
        cmd = [
            "ffmpeg",
            "-v",
            "quiet",
            "-y",
            "-i",
            str(source_path),
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(DEFAULT_SAMPLE_RATE),
            "-f",
            "s16le",
            "-",
        ]
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="ignore")
        logger.error("FFmpeg conversion failed: %s", detail)
        raise RuntimeError("音频转换为标准 PCM 失败") from exc
    finally:
        try:
            source_path.unlink(missing_ok=True)
        except OSError:
            pass



def _filename_for_mime(mime_type: str) -> str:
    normalized = (mime_type or "").lower()
    if "ogg" in normalized:
        return "audio.ogg"
    if "mp4" in normalized or "m4a" in normalized:
        return "audio.m4a"
    if "mpeg" in normalized or "mp3" in normalized:
        return "audio.mp3"
    if "wav" in normalized:
        return "audio.wav"
    return "audio.webm"
