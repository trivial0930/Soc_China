#!/bin/bash
# Offline Chinese TTS for the inspection robot's voice broadcast.
#   sherpa-onnx Matcha synth  ->  ffmpeg 48k stereo + gain  ->  aplay on USB speaker
#
# Deploy to /root/sherpa_say.sh on the RDK X5. voice_node calls it via the
# injection-safe "command" engine: subprocess [/root/sherpa_say.sh, TEXT] — the
# text arrives as $1 (no shell interpolation here or in the node).
#
# Assets in /root/sherpa/ (see docs/architecture/voice_broadcast_setup.md):
#   sherpa-onnx-offline-tts, matcha-icefall-zh-baker/, vocos-22khz-univ.onnx
# USB speaker = card 0 (Jieli CD002-AUDIO, 48000Hz stereo only) -> hw:0,0.
#
# Usage: sherpa_say.sh "三号工位电烙铁未关闭，请立即处理"
set -u
T="$1"
S=/root/sherpa
M="$S/matcha-icefall-zh-baker"
W=$(mktemp /tmp/voiceXXXXXX.wav)
W48="${W%.wav}_48.wav"

"$S/sherpa-onnx-offline-tts" \
  --matcha-acoustic-model="$M/model-steps-3.onnx" \
  --matcha-vocoder="$S/vocos-22khz-univ.onnx" \
  --matcha-lexicon="$M/lexicon.txt" \
  --matcha-tokens="$M/tokens.txt" \
  --matcha-dict-dir="$M/dict" \
  --tts-rule-fsts="$M/date.fst,$M/phone.fst,$M/number.fst" \
  --num-threads=8 \
  --output-filename="$W" \
  "$T" >/dev/null 2>&1

# Device is 48000/stereo-only; resample + boost level, then play direct (no plug).
ffmpeg -y -i "$W" -af "volume=4.5,alimiter=limit=0.97" -ar 48000 -ac 2 "$W48" >/dev/null 2>&1
aplay -D hw:0,0 "$W48" >/dev/null 2>&1

rm -f "$W" "$W48"
