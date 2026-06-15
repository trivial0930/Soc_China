# 本地 Qwen VLM(Layer 2)部署与联通

L2 本地认知用 **Qwen3-VL（8B）经 Ollama** 提供 OpenAI 兼容服务,由 `LocalVLMBackend`
通过 HTTP 调用。换运行机器**只改 `cognition.yaml` 的 `vlm_base_url`,不动代码**。

- **开发(暂无 RDK)**:就在 **Mac（M5 Pro / 24GB）** 本机跑,`vlm_base_url=http://localhost:11434/v1`。
- **部署/演示**:跑在 **Windows RTX 4080 Laptop**(常驻、和 RDK 同局域网),RDK 把
  `vlm_base_url` 指到 `http://<win-ip>:11434/v1`。

> 模型 tag:优先 `qwen3-vl:8b`;Ollama 库若还没有该 tag,退 `qwen2.5vl:7b`,或在 4080 上用 vLLM 跑 Qwen3-VL。
> 实际可拉的 tag 以 `ollama.com/library` / `ollama list` 为准。

## A. Mac 开发机(本机跑,localhost)

```bash
# 1) 安装 Ollama(macOS)
brew install ollama            # 或从 https://ollama.com 下载

# 2) 起服务(前台留一个终端,或用 brew services 后台)
ollama serve                   # 默认监听 127.0.0.1:11434

# 3) 拉模型(另开终端)
ollama pull qwen3-vl:8b   ||   ollama pull qwen2.5vl:7b   # 取拉得到的那个

# 4) 命令行先验模型本身能跑
ollama run qwen3-vl:8b "你好，用一句话说明你能做什么"

# 5) Python 端依赖(LocalVLMBackend 的真实 transport 用 openai SDK)
pip install openai

# 6) 真模型烟雾测试(喂一条样例事件 + 一张图,走 LocalVLMBackend)
python3 rdk_x5/scripts/qwen_local_smoke.py --image <某张jpg>
```

`cognition.yaml` 里 `backend: local_vlm`、`vlm_base_url: http://localhost:11434/v1` 即可。

## B. Windows 4080 部署机(局域网服务器)

```powershell
# 1) 装 Ollama for Windows(自带 CUDA,自动用 4080):https://ollama.com/download
# 2) 暴露到局域网 + 起服务(管理员 PowerShell)
setx OLLAMA_HOST "0.0.0.0:11434"     # 重开终端生效;让 RDK 能连
# 防火墙放行 11434(入站 TCP)
New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow
ollama serve
# 3) 拉模型
ollama pull qwen3-vl:8b            # 或 qwen2.5vl:7b
```

RDK / Mac 端把 `cognition.yaml` 改成:
```yaml
backend: local_vlm
vlm_base_url: "http://<win-ip>:11434/v1"   # <win-ip> = 4080 机器局域网 IP
```
连通性自检:`curl http://<win-ip>:11434/v1/models`。

## 显存/选型备注
- 4080 Laptop = 12GB VRAM,`qwen3-vl:8b` Q4(~6GB)余量充足;再大(32B)放不下。
- Mac M5 Pro 24GB 统一内存:8B 流畅,且有余量上 14B 量化。
- L3 云端(`report_service`,Qwen3-VL-Plus 百炼)与此独立,只需 `DASHSCOPE_API_KEY`。
